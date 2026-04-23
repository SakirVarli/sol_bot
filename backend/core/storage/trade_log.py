"""
Persists Position records and generates trade summaries.
"""
from __future__ import annotations

import json
from pathlib import Path

from loguru import logger

from core.models.position import Position
from core.storage.db import Database


class TradeLog:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def upsert_position(self, position: Position) -> None:
        data_json = position.model_dump_json()
        await self._db.execute(
            """
            INSERT OR REPLACE INTO positions
                (position_id, mint, mode, strategy_id, strategy_name, ledger_type, status, entry_ts, close_ts,
                 cost_sol, realized_pnl_sol, exit_reason, exit_reason_detail, data, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, unixepoch('now'))
            """,
            (
                position.position_id,
                position.mint,
                position.mode,
                position.strategy_id,
                position.strategy_name,
                position.ledger_type,
                position.status.value,
                position.entry_ts,
                position.close_ts,
                position.cost_sol,
                position.realized_pnl_sol,
                position.exit_reason.value if position.exit_reason else None,
                position.exit_reason_detail,
                data_json,
            ),
        )

    async def get_position(self, position_id: str) -> dict | None:
        return await self._db.fetchone(
            "SELECT * FROM positions WHERE position_id = ?",
            (position_id,),
        )

    async def get_open_positions(self) -> list[dict]:
        return await self._db.fetchall(
            "SELECT * FROM positions WHERE status IN ('PENDING', 'OPEN', 'PARTIAL_EXIT')"
        )

    async def get_closed_positions(self, limit: int = 100) -> list[dict]:
        return await self._db.fetchall(
            "SELECT * FROM positions WHERE status = 'CLOSED' ORDER BY close_ts DESC LIMIT ?",
            (limit,),
        )

    async def summary(self) -> dict:
        """Quick P&L summary for the current session."""
        rows = await self._db.fetchall(
            "SELECT realized_pnl_sol, exit_reason FROM positions WHERE status = 'CLOSED'"
        )
        if not rows:
            return {"trades": 0, "net_pnl_sol": 0.0, "win_rate": 0.0}

        total = len(rows)
        net_pnl = sum(r["realized_pnl_sol"] or 0.0 for r in rows)
        wins = sum(1 for r in rows if (r["realized_pnl_sol"] or 0.0) > 0)

        return {
            "trades": total,
            "net_pnl_sol": net_pnl,
            "win_rate": wins / total if total > 0 else 0.0,
            "winners": wins,
            "losers": total - wins,
        }

    async def summary_by_strategy(self) -> list[dict]:
        rows = await self._db.fetchall(
            """
            SELECT strategy_id, strategy_name,
                   COUNT(*) as trades,
                   SUM(CASE WHEN realized_pnl_sol > 0 THEN 1 ELSE 0 END) as winners,
                   SUM(CASE WHEN realized_pnl_sol <= 0 THEN 1 ELSE 0 END) as losers,
                   SUM(realized_pnl_sol) as net_pnl_sol
            FROM positions
            WHERE status = 'CLOSED'
            GROUP BY strategy_id, strategy_name
            ORDER BY net_pnl_sol DESC
            """
        )
        result = []
        for row in rows:
            trades = row["trades"] or 0
            winners = row["winners"] or 0
            result.append(
                {
                    "strategy_id": row["strategy_id"],
                    "strategy_name": row["strategy_name"],
                    "trades": trades,
                    "winners": winners,
                    "losers": row["losers"] or 0,
                    "net_pnl_sol": row["net_pnl_sol"] or 0.0,
                    "win_rate": winners / trades if trades else 0.0,
                }
            )
        return result

    async def per_exit_reason_breakdown(self) -> dict:
        rows = await self._db.fetchall(
            """
            SELECT exit_reason, COUNT(*) as count, SUM(realized_pnl_sol) as total_pnl
            FROM positions
            WHERE status = 'CLOSED'
            GROUP BY exit_reason
            """
        )
        return {r["exit_reason"]: {"count": r["count"], "pnl": r["total_pnl"]} for r in rows}
