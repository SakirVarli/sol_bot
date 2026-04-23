"""
Writes TradeEvents to the database and to rotating log files.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from loguru import logger

from core.models.trade_event import TradeEvent
from core.storage.db import Database


class EventLog:
    def __init__(self, db: Database, log_dir: Path) -> None:
        self._db = db
        self._log_dir = log_dir
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._queue: asyncio.Queue[TradeEvent] = asyncio.Queue()

    async def log(self, event: TradeEvent) -> None:
        """Non-blocking — puts event on the queue."""
        await self._queue.put(event)

    async def run(self) -> None:
        """Background task: drain the queue and persist events."""
        while True:
            event = await self._queue.get()
            try:
                await self._persist(event)
            except Exception as e:
                logger.error(f"EventLog persist error: {e}")
            finally:
                self._queue.task_done()

    async def _persist(self, event: TradeEvent) -> None:
        data_json = json.dumps(event.details, default=str)
        await self._db.execute(
            """
            INSERT OR REPLACE INTO trade_events
                (event_id, mint, event_type, ts, position_id, strategy_id, strategy_name, ledger_type, pnl_sol, pnl_pct, data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.event_id,
                event.mint,
                event.event_type,
                event.ts,
                event.position_id,
                event.strategy_id,
                event.strategy_name,
                event.ledger_type,
                event.pnl_sol,
                event.pnl_pct,
                data_json,
            ),
        )

        # Also log to file for easy tailing
        log_line = (
            f"{event.ts:.3f} | {event.event_type:<20} | "
            f"mint={event.mint[:8]}… | {event.details}"
        )
        if event.pnl_sol is not None:
            log_line += f" | pnl={event.pnl_sol:+.4f} SOL ({event.pnl_pct:+.1f}%)"

        logger.bind(event_type=event.event_type).info(log_line)

    async def get_events_for_mint(self, mint: str) -> list[dict]:
        return await self._db.fetchall(
            "SELECT * FROM trade_events WHERE mint = ? ORDER BY ts",
            (mint,),
        )

    async def get_recent_events(self, limit: int = 50) -> list[dict]:
        return await self._db.fetchall(
            "SELECT * FROM trade_events ORDER BY ts DESC LIMIT ?",
            (limit,),
        )
