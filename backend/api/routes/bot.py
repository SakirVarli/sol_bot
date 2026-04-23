"""
Bot control endpoints: start, stop, status, settings.
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.state import app_state

router = APIRouter()


class StartRequest(BaseModel):
    mode: str = "paper"


@router.get("/status")
async def get_status():
    pos_mgr = app_state.position_mgr
    open_positions = []
    if pos_mgr:
        open_positions = [
            {
                "position_id": p.position_id,
                "mint": p.mint,
                "entry_price": p.entry_price,
                "current_price": p.current_price,
                "pnl_pct": round(p.pnl_pct(), 2),
                "pnl_sol": round(p.realized_pnl_sol + p.unrealized_pnl_sol, 6),
                "status": p.status.value,
                "hold_seconds": round(p.hold_seconds(), 1),
                "tp1_triggered": p.tp1_triggered,
                "cost_sol": p.cost_sol,
            }
            for p in pos_mgr.get_open_positions()
        ]

    detector = app_state.detector
    pipeline = {"filtering": [], "watching": []}
    if detector:
        watching = detector.get_watching()
        pipeline["watching"] = [
            {
                "mint": c.mint,
                "source": c.source,
                "liquidity_usd": round(c.liquidity_usd, 0),
                "swap_count": c.swap_count,
                "watch_elapsed_seconds": round(c.watch_elapsed_seconds(), 1),
                "price_change_pct": round(c.price_change_pct() or 0, 2),
                "retrace_pct": round(c.retrace_from_peak_pct() or 0, 2),
                "state": c.state.value,
            }
            for c in watching
        ]

    stats = {"trades": 0, "win_rate": 0.0, "net_pnl_sol": 0.0, "winners": 0, "losers": 0}
    if app_state.trade_log:
        stats = await app_state.trade_log.summary()

    return {
        **app_state.to_dict(),
        "balance_sol": round(app_state.paper_balance_sol, 6),
        "initial_balance_sol": app_state.paper_initial_sol,
        "positions": open_positions,
        "pipeline": pipeline,
        "stats": stats,
    }


@router.post("/start")
async def start_bot(req: StartRequest):
    if app_state.running:
        raise HTTPException(status_code=400, detail="Bot is already running")

    from bot_runner import run_bot

    app_state.mode = req.mode
    app_state.stop_reason = None

    task = asyncio.create_task(run_bot(mode=req.mode, config=app_state.config))
    app_state.bot_task = task

    def on_done(fut: asyncio.Future):
        app_state.running = False
        app_state.bot_task = None
        if fut.cancelled():
            app_state.stop_reason = "stopped"
        elif fut.exception():
            app_state.stop_reason = str(fut.exception())

    task.add_done_callback(on_done)

    return {"status": "starting", "mode": req.mode}


@router.post("/stop")
async def stop_bot():
    if not app_state.running:
        raise HTTPException(status_code=400, detail="Bot is not running")

    task = app_state.bot_task
    if task and not task.done():
        task.cancel()
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=5.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass

    app_state.running = False
    app_state.bot_task = None
    app_state.stop_reason = "manually stopped"
    return {"status": "stopped"}


@router.get("/config")
async def get_config():
    """Return current config (safe subset — no keys/secrets)."""
    cfg = app_state.config
    return {
        "filters": cfg.get("filters", {}),
        "strategy": cfg.get("strategy", {}),
        "position": cfg.get("position", {}),
        "risk": cfg.get("risk", {}),
        "paper": cfg.get("paper", {}),
    }
