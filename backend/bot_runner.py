"""
Bot runner — called as an asyncio.Task by the API.

Sets up all components, registers the loguru → WebSocket sink,
populates AppState so API routes can read live data.
"""
from __future__ import annotations

import asyncio
import time
from pathlib import Path

from loguru import logger

from api.broadcaster import broadcaster
from api.state import app_state
from core.discovery.launch_detector import LaunchDetector
from core.filters.token_score import FilterPipeline
from core.models.signal import SignalType
from core.portfolio.position_manager import PositionManager
from core.storage.db import Database
from core.storage.event_log import EventLog
from core.storage.trade_log import TradeLog
from core.strategy.first_pullback import FirstPullbackStrategy
from core.utils.config_loader import get_rpc_http, get_rpc_ws
from core.utils.rpc_client import SolanaRPC


async def run_bot(mode: str = "paper", config: dict | None = None) -> None:
    if config is None:
        config = app_state.config

    rpc_http = get_rpc_http(config)
    rpc_ws = get_rpc_ws(config)
    data_dir = Path(config.get("bot", {}).get("data_dir", "data"))

    paper_cfg = config.get("paper", {})
    balance_sol = paper_cfg.get("initial_balance_sol", 10.0)
    trade_size_sol = paper_cfg.get("trade_size_sol", 0.1)

    # Register the WebSocket log sink
    sink_id = logger.add(broadcaster.loguru_sink, level="DEBUG", format="{message}")

    logger.info(f"Bot starting | mode={mode} rpc={rpc_http[:40]}…")

    # ── Infrastructure ────────────────────────────────────────────────────────
    db = Database(data_dir / "trades" / f"{mode}.db")
    await db.connect()

    event_queue: asyncio.Queue = asyncio.Queue()
    ready_queue: asyncio.Queue = asyncio.Queue()

    event_log = EventLog(db=db, log_dir=data_dir / "logs")
    trade_log = TradeLog(db=db)

    rpc = SolanaRPC(rpc_http)
    filter_pipeline = FilterPipeline(rpc=rpc, settings=config)

    detector = LaunchDetector(
        rpc_http=rpc_http,
        rpc_ws=rpc_ws,
        filter_pipeline=filter_pipeline,
        ready_queue=ready_queue,
        event_queue=event_queue,
        settings=config,
    )

    strategy = FirstPullbackStrategy(config=config, trade_size_sol=trade_size_sol)

    position_mgr = PositionManager(
        trade_log=trade_log,
        event_queue=event_queue,
        settings=config,
        mode=mode,
    )

    # ── Populate AppState ─────────────────────────────────────────────────────
    app_state.running = True
    app_state.mode = mode
    app_state.start_time = time.time()
    app_state.detector = detector
    app_state.position_mgr = position_mgr
    app_state.trade_log = trade_log
    app_state.paper_balance_sol = balance_sol
    app_state.paper_initial_sol = balance_sol

    # ── Strategy evaluation loop ──────────────────────────────────────────────
    async def strategy_loop() -> None:
        while True:
            await asyncio.sleep(1)
            for candidate in detector.get_watching():
                if not strategy.is_ready(candidate):
                    continue
                if not position_mgr.can_enter():
                    continue

                signal = await strategy.evaluate(candidate)
                if signal is None or signal.signal_type != SignalType.ENTER:
                    continue

                price = candidate.current_price or 0
                if price <= 0:
                    continue

                pos = await position_mgr.on_signal(signal, price)
                if pos:
                    strategy.reset(candidate.mint)
                    detector._swap_listener.watch(
                        candidate.mint,
                        on_price_update=lambda mint, p: asyncio.create_task(
                            position_mgr.on_price_update(mint, p)
                        ),
                    )
                    # Update paper balance tracking
                    app_state.paper_balance_sol -= pos.cost_sol

    # ── State broadcast loop ──────────────────────────────────────────────────
    async def state_broadcast_loop() -> None:
        from api.routes.bot import get_status
        from api.routes.trades import get_trade_history

        while True:
            await asyncio.sleep(2)
            try:
                state = await get_status()
                await broadcaster.broadcast_state(state)

                history = await get_trade_history(limit=50)
                await broadcaster.broadcast_history(history)
            except Exception as e:
                logger.debug(f"State broadcast error: {e}")

    # ── Run everything ────────────────────────────────────────────────────────
    try:
        await asyncio.gather(
            detector.run(),
            event_log.run(),
            strategy_loop(),
            state_broadcast_loop(),
        )
    except asyncio.CancelledError:
        logger.info("Bot stopped")
    finally:
        # Cleanup
        logger.remove(sink_id)
        app_state.running = False
        app_state.detector = None
        app_state.position_mgr = None
        app_state.trade_log = None
        await db.close()
        await filter_pipeline.close()
