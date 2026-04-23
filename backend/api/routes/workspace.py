from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException

from api.runtime import runtime_state

router = APIRouter()


@router.get("/status")
async def get_workspace_status():
    if runtime_state.supervisor:
        return await runtime_state.supervisor.workspace_status()
    return {
        "running": runtime_state.running,
        "uptime_seconds": runtime_state.uptime_seconds(),
        "stop_reason": runtime_state.stop_reason,
        "portfolio": {"ledgers": [], "strategies": {}},
        "positions": [],
        "pipeline": {"filtering": [], "watching": []},
        "stats": {"trades": 0, "win_rate": 0.0, "net_pnl_sol": 0.0, "winners": 0, "losers": 0},
        "strategies": [],
    }


@router.post("/start")
async def start_workspace():
    if runtime_state.running:
        raise HTTPException(status_code=400, detail="Workspace is already running")
    from workspace_runner import run_workspace

    task = asyncio.create_task(run_workspace(config=runtime_state.config))
    runtime_state.bot_task = task
    runtime_state.stop_reason = None

    def on_done(fut: asyncio.Future) -> None:
        runtime_state.running = False
        runtime_state.bot_task = None
        if fut.cancelled():
            runtime_state.stop_reason = "stopped"
        elif fut.exception():
            runtime_state.stop_reason = str(fut.exception())

    task.add_done_callback(on_done)
    return {"status": "starting"}


@router.post("/stop")
async def stop_workspace():
    if not runtime_state.running:
        raise HTTPException(status_code=400, detail="Workspace is not running")
    runtime_state.stop_reason = "manually stopped"
    task = runtime_state.bot_task
    if task and not task.done():
        task.cancel()
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=5.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass
    runtime_state.running = False
    runtime_state.bot_task = None
    return {"status": "stopped"}


@router.get("/config")
async def get_workspace_config():
    cfg = runtime_state.config
    return {
        "filters": cfg.get("filters", {}),
        "strategy": cfg.get("strategy", {}),
        "position": cfg.get("position", {}),
        "risk": cfg.get("risk", {}),
        "paper": cfg.get("paper", {}),
        "live": cfg.get("live", {}),
    }
