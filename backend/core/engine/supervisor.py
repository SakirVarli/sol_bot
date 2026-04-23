from __future__ import annotations

import asyncio
import time
from pathlib import Path

from loguru import logger

from api.broadcaster import broadcaster
from core.discovery.launch_detector import LaunchDetector
from core.engine.candle_service import CandleService
from core.engine.portfolio_allocator import PortfolioAllocator
from core.engine.rule_engine import RuleCompiler, RuleEvaluator, StrategyMemory
from core.engine.strategy_store import StrategyStore
from core.filters.token_score import FilterPipeline
from core.models.position import ExitReason, Position
from core.models.signal import Signal, SignalType
from core.models.strategy import StrategyDefinition, StrategyInstance, StrategyStats, StrategyStatus
from core.portfolio.multi_position_manager import MultiStrategyPositionManager
from core.storage.db import Database
from core.storage.event_log import EventLog
from core.storage.trade_log import TradeLog
from core.utils.config_loader import get_rpc_http, get_rpc_ws
from core.utils.ids import signal_id
from core.utils.rpc_client import SolanaRPC


class EngineSupervisor:
    def __init__(self, config: dict) -> None:
        self.config = config
        self.running = False
        self.start_time: float | None = None
        self.stop_reason: str | None = None

        self._tasks: list[asyncio.Task] = []
        self._db: Database | None = None
        self._event_queue: asyncio.Queue = asyncio.Queue()
        self._event_log: EventLog | None = None
        self._trade_log: TradeLog | None = None
        self._store: StrategyStore | None = None
        self._detector: LaunchDetector | None = None
        self._position_mgr: MultiStrategyPositionManager | None = None
        self._allocator: PortfolioAllocator | None = None
        self._filter_pipeline: FilterPipeline | None = None
        self._candle_service = CandleService()
        self._compiler = RuleCompiler()
        self._evaluator = RuleEvaluator()

        self._definitions: dict[str, StrategyDefinition] = {}
        self._instances: dict[str, StrategyInstance] = {}
        self._memories: dict[tuple[str, str], StrategyMemory] = {}
        self._watched_callbacks: set[str] = set()

    @property
    def trade_log(self) -> TradeLog | None:
        return self._trade_log

    @property
    def detector(self) -> LaunchDetector | None:
        return self._detector

    @property
    def position_mgr(self) -> MultiStrategyPositionManager | None:
        return self._position_mgr

    async def start(self) -> None:
        if self.running:
            return

        rpc_http = get_rpc_http(self.config)
        rpc_ws = get_rpc_ws(self.config)
        data_dir = Path(self.config.get("bot", {}).get("data_dir", "data"))
        paper_balance_sol = float(self.config.get("paper", {}).get("initial_balance_sol", 10.0))
        live_balance_sol = float(self.config.get("live", {}).get("initial_balance_sol", paper_balance_sol))

        self._db = Database(data_dir / "trades" / "workspace.db")
        await self._db.connect()
        self._event_log = EventLog(db=self._db, log_dir=data_dir / "logs")
        self._trade_log = TradeLog(db=self._db)
        self._store = StrategyStore(self._db)

        definitions, instances = await self._store.ensure_seed_data(self.config)
        self._definitions = {definition.definition_id: definition for definition in definitions}
        self._instances = {instance.strategy_id: instance for instance in instances}

        self._allocator = PortfolioAllocator(paper_balance_sol=paper_balance_sol, live_balance_sol=live_balance_sol)
        for instance in self._instances.values():
            self._allocator.upsert_strategy(instance)
            definition = self._definitions.get(instance.definition_id)
            if definition:
                self._candle_service.register_timeframe(definition.candle_seconds)

        rpc = SolanaRPC(rpc_http)
        filter_pipeline = FilterPipeline(rpc=rpc, settings=self.config)
        self._filter_pipeline = filter_pipeline
        self._detector = LaunchDetector(
            rpc_http=rpc_http,
            rpc_ws=rpc_ws,
            filter_pipeline=filter_pipeline,
            ready_queue=asyncio.Queue(),
            event_queue=self._event_queue,
            settings=self.config,
        )
        self._position_mgr = MultiStrategyPositionManager(
            trade_log=self._trade_log,
            event_queue=self._event_queue,
            settings=self.config,
        )

        self.start_time = time.time()
        self.stop_reason = None
        self.running = True

        self._tasks = [
            asyncio.create_task(self._event_log.run(), name="event_log"),
            asyncio.create_task(self._event_pump(), name="event_pump"),
            asyncio.create_task(self._detector.run(), name="launch_detector"),
            asyncio.create_task(self._strategy_loop(), name="strategy_loop"),
            asyncio.create_task(self._broadcast_loop(), name="broadcast_loop"),
        ]
        logger.info("EngineSupervisor started")

    async def stop(self, reason: str = "manually stopped") -> None:
        self.stop_reason = reason
        self.running = False
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=5.0)
            except Exception:
                pass
        self._tasks = []
        if self._db:
            await self._db.close()
        if self._filter_pipeline:
            await self._filter_pipeline.close()

    async def list_definitions(self) -> list[StrategyDefinition]:
        if self._store:
            self._definitions = {d.definition_id: d for d in await self._store.list_definitions()}
        return list(self._definitions.values())

    async def list_instances(self) -> list[StrategyInstance]:
        if self._store:
            self._instances = {s.strategy_id: s for s in await self._store.list_instances()}
        return list(self._instances.values())

    async def save_definition(self, definition: StrategyDefinition) -> StrategyDefinition:
        compiled = self._compiler.compile(definition)
        if self._store:
            await self._store.upsert_definition(compiled)
        self._definitions[compiled.definition_id] = compiled
        self._candle_service.register_timeframe(compiled.candle_seconds)
        return compiled

    async def save_instance(self, instance: StrategyInstance) -> StrategyInstance:
        if self._store:
            await self._store.upsert_instance(instance)
        self._instances[instance.strategy_id] = instance
        if self._allocator:
            self._allocator.upsert_strategy(instance)
        definition = self._definitions.get(instance.definition_id)
        if definition:
            self._candle_service.register_timeframe(definition.candle_seconds)
        return instance

    async def delete_instance(self, strategy_id: str) -> bool:
        instance = self._instances.get(strategy_id)
        if instance is None:
            return False
        if self._position_mgr and self._position_mgr.get_positions_for_strategy(strategy_id):
            raise ValueError("Stop and close all open positions before deleting this strategy instance.")
        if self._store:
            deleted = await self._store.delete_instance(strategy_id)
            if not deleted:
                return False
        self._instances.pop(strategy_id, None)
        self._memories = {
            key: memory
            for key, memory in self._memories.items()
            if key[0] != strategy_id
        }
        return True

    async def delete_definition(self, definition_id: str) -> bool:
        if any(instance.definition_id == definition_id for instance in self._instances.values()):
            raise ValueError("Delete all strategy instances using this definition before deleting the definition.")
        if self._store:
            deleted = await self._store.delete_definition(definition_id)
            if not deleted:
                return False
        self._definitions.pop(definition_id, None)
        return True

    async def set_strategy_status(self, strategy_id: str, status: StrategyStatus) -> StrategyInstance | None:
        instance = self._instances.get(strategy_id)
        if instance is None:
            return None
        instance.status = status
        if status == StrategyStatus.ENABLED:
            instance.last_started_ts = time.time()
        else:
            instance.last_stopped_ts = time.time()
        return await self.save_instance(instance)

    def validate_definition(self, definition: StrategyDefinition) -> dict:
        return {
            "errors": self._compiler.validate(definition),
            "entry_summary": self._compiler.summarize(definition.entry),
            "exit_summary": self._compiler.summarize(definition.exits),
        }

    async def preview_definition(self, definition: StrategyDefinition) -> list[dict]:
        previews: list[dict] = []
        if self._detector is None:
            return previews
        for candidate in self._detector.get_watching():
            candles = self._candle_service.get_candles(candidate.mint, definition.candle_seconds)
            memory = self._memories.setdefault((definition.definition_id, candidate.mint), StrategyMemory())
            result = self._evaluator.evaluate_group(definition.entry, candles, None, memory, candidate.mint)
            previews.append(
                {
                    "mint": candidate.mint,
                    "candles": len(candles),
                    "entry_match": result.matched,
                    "reason": result.reason,
                }
            )
        return previews

    async def workspace_status(self) -> dict:
        allocator_snapshot = self._allocator.snapshot() if self._allocator else {"ledgers": [], "strategies": {}}
        positions = self._position_mgr.get_open_positions() if self._position_mgr else []
        strategy_stats = await self.strategy_stats()
        pipeline = {"filtering": [], "watching": []}
        if self._detector:
            pipeline["watching"] = [
                {
                    "mint": candidate.mint,
                    "source": candidate.source,
                    "liquidity_usd": round(candidate.liquidity_usd, 0),
                    "swap_count": candidate.swap_count,
                    "watch_elapsed_seconds": round(candidate.watch_elapsed_seconds(), 1),
                    "price_change_pct": round(candidate.price_change_pct() or 0, 2),
                    "retrace_pct": round(candidate.retrace_from_peak_pct() or 0, 2),
                    "state": candidate.state.value,
                }
                for candidate in self._detector.get_watching()
            ]
        portfolio_stats = await self._trade_log.summary() if self._trade_log else {"trades": 0, "win_rate": 0.0, "net_pnl_sol": 0.0, "winners": 0, "losers": 0}
        return {
            "running": self.running,
            "uptime_seconds": 0.0 if self.start_time is None else time.time() - self.start_time,
            "stop_reason": self.stop_reason,
            "portfolio": allocator_snapshot,
            "positions": [self._serialize_position(position) for position in positions],
            "pipeline": pipeline,
            "stats": portfolio_stats,
            "strategies": [stat.model_dump() for stat in strategy_stats],
        }

    async def strategy_stats(self) -> list[StrategyStats]:
        if not self._allocator:
            return []
        positions = self._position_mgr.get_open_positions() if self._position_mgr else []
        closed_rows = await self._trade_log.summary_by_strategy() if self._trade_log else []
        closed_lookup = {row["strategy_id"]: row for row in closed_rows}
        stats: list[StrategyStats] = []
        for instance in self._instances.values():
            allocation = self._allocator.snapshot()["strategies"].get(instance.strategy_id, {})
            strategy_positions = [pos for pos in positions if pos.strategy_id == instance.strategy_id]
            unrealized = sum(pos.unrealized_pnl_sol for pos in strategy_positions)
            row = closed_lookup.get(instance.strategy_id, {})
            stats.append(
                StrategyStats(
                    strategy_id=instance.strategy_id,
                    strategy_name=instance.name,
                    mode=instance.mode,
                    trades=row.get("trades", 0),
                    winners=row.get("winners", 0),
                    losers=row.get("losers", 0),
                    win_rate=row.get("win_rate", 0.0),
                    realized_pnl_sol=row.get("net_pnl_sol", 0.0),
                    unrealized_pnl_sol=unrealized,
                    open_positions=len(strategy_positions),
                    used_budget_sol=allocation.get("used_sol", 0.0),
                    reserved_budget_sol=allocation.get("reserved_sol", instance.reserved_budget_sol),
                    free_budget_sol=allocation.get("free_sol", instance.reserved_budget_sol),
                )
            )
        return stats

    async def _strategy_loop(self) -> None:
        seen_mints: set[str] = set()
        while True:
            await asyncio.sleep(1)
            if self._detector is None or self._position_mgr is None or self._allocator is None:
                continue

            for candidate in self._detector.get_watching():
                if candidate.mint not in seen_mints:
                    self._detector._swap_listener.watch(candidate.mint, self._on_market_price)
                    seen_mints.add(candidate.mint)

                for instance in self._instances.values():
                    if instance.status != StrategyStatus.ENABLED:
                        continue
                    definition = self._definitions.get(instance.definition_id)
                    if definition is None:
                        continue
                    candles = self._candle_service.get_candles(candidate.mint, definition.candle_seconds)
                    if not candles:
                        continue
                    if self._position_mgr.has_open_position(instance.strategy_id, candidate.mint):
                        for position in self._position_mgr.get_positions_for_strategy(instance.strategy_id):
                            if position.mint != candidate.mint:
                                continue
                            result = self._evaluator.evaluate_group(
                                definition.exits,
                                candles,
                                position,
                                self._memories.setdefault((instance.strategy_id, candidate.mint), StrategyMemory()),
                                candidate.mint,
                            )
                            if result.matched:
                                realized_delta = await self._position_mgr.close_position(position, ExitReason.RULE, result.reason)
                                self._allocator.release(instance.strategy_id, position.allocation_reserved_sol, realized_delta)
                                self._memories[(instance.strategy_id, candidate.mint)].last_exit_ts_by_mint[candidate.mint] = time.time()
                            else:
                                standard = await self._position_mgr.apply_standard_exits(position)
                                if standard:
                                    self._allocator.release(
                                        instance.strategy_id,
                                        standard["released_size"],
                                        standard["realized_pnl_sol"],
                                    )
                                    if standard["closed"]:
                                        self._memories[(instance.strategy_id, candidate.mint)].last_exit_ts_by_mint[candidate.mint] = time.time()
                        continue

                    if not self._is_reentry_allowed(instance, candidate.mint):
                        continue
                    entry_result = self._evaluator.evaluate_group(
                        definition.entry,
                        candles,
                        None,
                        self._memories.setdefault((instance.strategy_id, candidate.mint), StrategyMemory()),
                        candidate.mint,
                    )
                    if not entry_result.matched:
                        continue
                    size_sol = self._resolve_position_size(instance, definition)
                    if size_sol <= 0 or not self._allocator.can_allocate(instance.strategy_id, size_sol):
                        continue
                    price = candidate.current_price or 0.0
                    if price <= 0:
                        continue
                    signal = Signal(
                        signal_id=signal_id(),
                        signal_type=SignalType.ENTER,
                        mint=candidate.mint,
                        strategy=instance.name,
                        strategy_id=instance.strategy_id,
                        strategy_name=instance.name,
                        mode=instance.mode.value,
                        ledger_type=instance.mode.value,
                        rule_version=definition.version,
                        entry_reason=entry_result.reason,
                        suggested_size_sol=size_sol,
                        liquidity_usd=candidate.liquidity_usd,
                        notes=entry_result.reason,
                    )
                    position = await self._position_mgr.open_position(
                        signal=signal,
                        current_price=price,
                        allocation_reserved_sol=size_sol,
                    )
                    if position:
                        self._allocator.reserve(instance.strategy_id, size_sol)
                        memory = self._memories.setdefault((instance.strategy_id, candidate.mint), StrategyMemory())
                        memory.entries_by_mint[candidate.mint] = memory.entries_by_mint.get(candidate.mint, 0) + 1

    def _on_market_price(self, mint: str, price: float) -> None:
        now = time.time()
        closed = self._candle_service.add_tick(mint=mint, price=price, ts=now)
        if closed:
            logger.debug(f"Candles closed for {mint[:8]}... count={len(closed)}")
        if self._position_mgr:
            asyncio.create_task(self._position_mgr.update_price(mint, price))

    async def _event_pump(self) -> None:
        while True:
            event = await self._event_queue.get()
            if self._event_log:
                await self._event_log.log(event)
            self._event_queue.task_done()

    async def _broadcast_loop(self) -> None:
        from api.routes.workspace_trades import get_trade_history
        while True:
            await asyncio.sleep(2)
            try:
                await broadcaster.broadcast_state(await self.workspace_status())
                await broadcaster.broadcast_history(await get_trade_history(limit=100))
            except Exception as exc:
                logger.debug(f"Broadcast loop error: {exc}")

    def _resolve_position_size(self, instance: StrategyInstance, definition: StrategyDefinition) -> float:
        sizing = definition.sizing or {}
        kind = sizing.get("kind", "fixed_sol")
        if kind == "allocation_pct":
            return instance.reserved_budget_sol * float(sizing.get("value", 0))
        size = float(sizing.get("value", self.config.get("paper", {}).get("trade_size_sol", 0.1)))
        max_size = float(sizing.get("max_size_sol", size))
        return min(size, max_size)

    def _is_reentry_allowed(self, instance: StrategyInstance, mint: str) -> bool:
        definition = self._definitions.get(instance.definition_id)
        if definition is None:
            return False
        memory = self._memories.setdefault((instance.strategy_id, mint), StrategyMemory())
        reentry = definition.reentry or {}
        if not reentry.get("allow_repeat_entries", True) and memory.entries_by_mint.get(mint, 0) > 0:
            return False
        cooldown = float(reentry.get("cooldown_seconds", 0))
        last_exit = memory.last_exit_ts_by_mint.get(mint)
        if last_exit and cooldown > 0 and (time.time() - last_exit) < cooldown:
            return False
        return True

    def _serialize_position(self, position: Position) -> dict:
        return {
            "position_id": position.position_id,
            "mint": position.mint,
            "strategy_id": position.strategy_id,
            "strategy_name": position.strategy_name,
            "ledger_type": position.ledger_type,
            "entry_price": position.entry_price,
            "current_price": position.current_price,
            "pnl_pct": round(position.pnl_pct(), 2),
            "pnl_sol": round(position.realized_pnl_sol + position.unrealized_pnl_sol, 6),
            "status": position.status.value,
            "hold_seconds": round(position.hold_seconds(), 1),
            "tp1_triggered": position.tp1_triggered,
            "cost_sol": position.cost_sol,
            "entry_reason": position.entry_reason,
        }
