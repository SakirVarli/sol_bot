from __future__ import annotations

import json

from fastapi import APIRouter

from api.runtime import runtime_state

router = APIRouter()


@router.get("/history")
async def get_trade_history(limit: int = 100):
    supervisor = runtime_state.supervisor
    if not supervisor or not supervisor.trade_log:
        return []
    rows = await supervisor.trade_log.get_closed_positions(limit=limit)
    result = []
    for row in rows:
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
        result.append(
            {
                "position_id": row["position_id"],
                "mint": row["mint"],
                "mode": row["mode"],
                "strategy_id": row.get("strategy_id"),
                "strategy_name": row.get("strategy_name"),
                "ledger_type": row.get("ledger_type"),
                "entry_ts": row.get("entry_ts"),
                "close_ts": row.get("close_ts"),
                "cost_sol": round(cost, 6),
                "realized_pnl_sol": round(pnl, 6),
                "pnl_pct": round(pnl_pct, 2),
                "exit_reason": row.get("exit_reason"),
                "exit_reason_detail": row.get("exit_reason_detail"),
                "hold_seconds": round(hold_sec, 1),
            }
        )
    return result


@router.get("/stats")
async def get_trade_stats():
    supervisor = runtime_state.supervisor
    if not supervisor or not supervisor.trade_log:
        return {}
    return {
        "summary": await supervisor.trade_log.summary(),
        "by_exit_reason": await supervisor.trade_log.per_exit_reason_breakdown(),
        "by_strategy": await supervisor.trade_log.summary_by_strategy(),
    }
