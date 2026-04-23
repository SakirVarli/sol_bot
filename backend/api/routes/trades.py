"""
Trade history and analytics endpoints.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException

from api.state import app_state

router = APIRouter()


@router.get("/history")
async def get_trade_history(limit: int = 100):
    if not app_state.trade_log:
        return []

    rows = await app_state.trade_log.get_closed_positions(limit=limit)
    result = []
    for row in rows:
        # Parse the full position from JSON blob for extra fields
        try:
            pos_data = json.loads(row.get("data", "{}"))
        except Exception:
            pos_data = {}

        hold_sec = 0.0
        if row.get("entry_ts") and row.get("close_ts"):
            hold_sec = row["close_ts"] - row["entry_ts"]

        cost = row.get("cost_sol") or pos_data.get("cost_sol") or 0
        pnl = row.get("realized_pnl_sol") or 0
        pnl_pct = (pnl / cost * 100) if cost > 0 else 0

        result.append({
            "position_id": row["position_id"],
            "mint": row["mint"],
            "mode": row["mode"],
            "entry_ts": row.get("entry_ts"),
            "close_ts": row.get("close_ts"),
            "cost_sol": round(cost, 6),
            "realized_pnl_sol": round(pnl, 6),
            "pnl_pct": round(pnl_pct, 2),
            "exit_reason": row.get("exit_reason"),
            "hold_seconds": round(hold_sec, 1),
        })
    return result


@router.get("/stats")
async def get_stats():
    if not app_state.trade_log:
        return {}

    summary = await app_state.trade_log.summary()
    breakdown = await app_state.trade_log.per_exit_reason_breakdown()
    return {"summary": summary, "by_exit_reason": breakdown}
