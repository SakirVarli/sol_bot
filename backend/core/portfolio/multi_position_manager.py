from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from typing import Optional

from loguru import logger

from core.models.position import ExitReason, PartialFill, Position, PositionStatus
from core.models.signal import Signal, SignalType
from core.models.trade_event import TradeEvent, position_closed_event
from core.storage.trade_log import TradeLog
from core.utils.ids import event_id, position_id
from core.utils.math_utils import stop_loss_price, take_profit_price, trailing_stop_price


class MultiStrategyPositionManager:
    def __init__(
        self,
        trade_log: TradeLog,
        event_queue: asyncio.Queue,
        settings: dict,
    ) -> None:
        self._log = trade_log
        self._event_q = event_queue
        self._positions: dict[str, Position] = {}
        self._positions_by_strategy: dict[str, set[str]] = defaultdict(set)
        self._positions_by_mint: dict[str, set[str]] = defaultdict(set)

        pos_cfg = settings.get("position", {})
        self._tp1_pct = pos_cfg.get("tp1_pct", 40.0)
        self._tp1_fraction = pos_cfg.get("tp1_sell_fraction", 0.5)
        self._trail_pct = pos_cfg.get("trailing_stop_pct", 25.0)
        self._hard_stop_pct = pos_cfg.get("hard_stop_pct", -15.0)
        self._max_hold_minutes = pos_cfg.get("max_hold_minutes", 10)

    def get_open_positions(self) -> list[Position]:
        return [
            position
            for position in self._positions.values()
            if position.status in (PositionStatus.PENDING, PositionStatus.OPEN, PositionStatus.PARTIAL_EXIT)
        ]

    def get_positions_for_strategy(self, strategy_id: str) -> list[Position]:
        ids = self._positions_by_strategy.get(strategy_id, set())
        return [self._positions[pos_id] for pos_id in ids if pos_id in self._positions]

    def has_open_position(self, strategy_id: str, mint: str) -> bool:
        for pos_id in self._positions_by_strategy.get(strategy_id, set()):
            position = self._positions.get(pos_id)
            if position and position.mint == mint and position.status in (
                PositionStatus.PENDING,
                PositionStatus.OPEN,
                PositionStatus.PARTIAL_EXIT,
            ):
                return True
        return False

    async def open_position(self, signal: Signal, current_price: float, allocation_reserved_sol: float) -> Optional[Position]:
        if signal.signal_type != SignalType.ENTER:
            return None
        fill_price = current_price * (1 + signal.suggested_slippage_bps / 10_000)
        quantity = signal.suggested_size_sol / fill_price if fill_price > 0 else 0.0
        position = Position(
            position_id=position_id(),
            mint=signal.mint,
            mode=signal.mode,
            ledger_type=signal.ledger_type,
            strategy_id=signal.strategy_id,
            strategy_name=signal.strategy_name or signal.strategy,
            rule_version=signal.rule_version,
            entry_reason=signal.entry_reason or signal.notes,
            allocation_reserved_sol=allocation_reserved_sol,
            entry_ts=time.time(),
            entry_price=fill_price,
            quantity=quantity,
            cost_sol=signal.suggested_size_sol,
            current_price=fill_price,
            highest_price=fill_price,
            status=PositionStatus.OPEN,
            tp1_price=take_profit_price(fill_price, self._tp1_pct),
            tp1_fraction=self._tp1_fraction,
            trailing_stop_pct=self._trail_pct,
            hard_stop_price=stop_loss_price(fill_price, self._hard_stop_pct),
            time_stop_ts=time.time() + self._max_hold_minutes * 60,
        )
        self._positions[position.position_id] = position
        self._positions_by_strategy[position.strategy_id].add(position.position_id)
        self._positions_by_mint[position.mint].add(position.position_id)
        await self._log.upsert_position(position)
        await self._event_q.put(
            TradeEvent(
                event_id=event_id(),
                mint=position.mint,
                event_type="BUY_FILLED",
                position_id=position.position_id,
                strategy_id=position.strategy_id,
                strategy_name=position.strategy_name,
                ledger_type=position.ledger_type,
                price=fill_price,
                liquidity_usd=signal.liquidity_usd,
                details={
                    "size_sol": signal.suggested_size_sol,
                    "quantity": quantity,
                    "entry_reason": position.entry_reason,
                },
            )
        )
        logger.info(
            f"[{position.ledger_type.upper()}] ENTERED | strategy={position.strategy_name} "
            f"mint={position.mint[:8]}... price={fill_price:.8f} size={signal.suggested_size_sol:.3f} SOL"
        )
        return position

    async def update_price(self, mint: str, price: float) -> None:
        for pos_id in list(self._positions_by_mint.get(mint, set())):
            position = self._positions.get(pos_id)
            if position is None or position.status not in (PositionStatus.OPEN, PositionStatus.PARTIAL_EXIT):
                continue
            position.update_price(price)
            await self._log.upsert_position(position)

    async def apply_standard_exits(self, position: Position) -> Optional[dict]:
        price = position.current_price
        if not position.tp1_triggered and price >= position.tp1_price:
            released_size, realized = await self._partial_exit(position, position.tp1_fraction, ExitReason.TP1, "take profit")
            position.tp1_triggered = True
            return {"action": "tp1", "released_size": released_size, "realized_pnl_sol": realized, "closed": False}
        if position.tp1_triggered:
            trail_price = trailing_stop_price(position.highest_price, position.trailing_stop_pct)
            if price <= trail_price:
                realized = await self.close_position(position, ExitReason.TRAILING_STOP, "trailing stop")
                return {"action": "trailing_stop", "released_size": position.allocation_reserved_sol, "realized_pnl_sol": realized, "closed": True}
        if price <= position.hard_stop_price:
            realized = await self.close_position(position, ExitReason.HARD_STOP, "hard stop")
            return {"action": "hard_stop", "released_size": position.allocation_reserved_sol, "realized_pnl_sol": realized, "closed": True}
        if position.is_past_time_stop():
            realized = await self.close_position(position, ExitReason.TIME_STOP, "time stop")
            return {"action": "time_stop", "released_size": position.allocation_reserved_sol, "realized_pnl_sol": realized, "closed": True}
        return None

    async def close_position(self, position: Position, reason: ExitReason, detail: str) -> float:
        sell_price = position.current_price
        proceeds_sol = position.quantity * sell_price
        realized_before = position.realized_pnl_sol
        position.realized_pnl_sol += proceeds_sol - position.cost_sol
        position.quantity = 0
        position.cost_sol = 0
        position.status = PositionStatus.CLOSED
        position.exit_reason = reason
        position.exit_reason_detail = detail
        position.close_ts = time.time()
        await self._log.upsert_position(position)
        await self._event_q.put(
            position_closed_event(
                event_id=event_id(),
                mint=position.mint,
                position_id=position.position_id,
                exit_reason=reason.value,
                pnl_sol=position.realized_pnl_sol,
                pnl_pct=position.pnl_pct(),
                hold_seconds=position.hold_seconds(),
            ).model_copy(
                update={
                    "strategy_id": position.strategy_id,
                    "strategy_name": position.strategy_name,
                    "ledger_type": position.ledger_type,
                    "details": {"exit_reason": reason.value, "detail": detail, "hold_seconds": position.hold_seconds()},
                }
            )
        )
        self._positions_by_strategy[position.strategy_id].discard(position.position_id)
        self._positions_by_mint[position.mint].discard(position.position_id)
        logger.info(
            f"[{position.ledger_type.upper()}] CLOSED | strategy={position.strategy_name} "
            f"mint={position.mint[:8]}... pnl={position.realized_pnl_sol:+.4f} SOL"
        )
        return position.realized_pnl_sol - realized_before

    async def _partial_exit(self, position: Position, fraction: float, reason: ExitReason, detail: str) -> tuple[float, float]:
        sell_qty = position.quantity * fraction
        sell_price = position.current_price
        proceeds_sol = sell_qty * sell_price
        cost_fraction = position.cost_sol * fraction
        realized_before = position.realized_pnl_sol
        position.realized_pnl_sol += proceeds_sol - cost_fraction
        position.quantity -= sell_qty
        position.cost_sol -= cost_fraction
        position.allocation_reserved_sol = max(0.0, position.allocation_reserved_sol - cost_fraction)
        position.status = PositionStatus.PARTIAL_EXIT
        position.exit_reason_detail = detail
        position.exit_fills.append(
            PartialFill(ts=time.time(), quantity=sell_qty, price=sell_price, reason=reason.value)
        )
        await self._log.upsert_position(position)
        return cost_fraction, position.realized_pnl_sol - realized_before
