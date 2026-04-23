"""
FastAPI application — serves REST API and WebSocket stream.
"""
from __future__ import annotations

import asyncio
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from api.broadcaster import broadcaster
from api.routes import bot, trades, websocket
from api.routes.strategies import router as strategies_router
from api.routes.workspace import router as workspace_router
from api.routes.workspace_trades import router as workspace_trades_router
from api.routes.workspace_websocket import router as workspace_websocket_router
from api.runtime import runtime_state
from core.utils.config_loader import load_config


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ───────────────────────────────────────────────────────────────
    config = load_config(Path(__file__).parent / "config")
    runtime_state.config = config

    # Configure loguru
    log_level = config.get("bot", {}).get("log_level", "INFO")
    logger.remove()
    logger.add(
        sys.stdout,
        level=log_level,
        format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}",
        colorize=True,
    )
    data_dir = Path(config.get("bot", {}).get("data_dir", "data"))
    (data_dir / "logs").mkdir(parents=True, exist_ok=True)
    logger.add(
        str(data_dir / "logs" / "bot_{time:YYYY-MM-DD}.log"),
        level="DEBUG",
        rotation="1 day",
        retention="14 days",
        compression="gz",
    )

    logger.info("SOL Meme Bot API starting…")

    # Start background tasks
    asyncio.create_task(broadcaster.run(), name="log_broadcaster")

    yield

    # ── Shutdown ──────────────────────────────────────────────────────────────
    logger.info("Shutting down…")
    broadcaster.stop()
    if runtime_state.bot_task and not runtime_state.bot_task.done():
        runtime_state.bot_task.cancel()


app = FastAPI(title="SOL Meme Bot", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(bot.router, prefix="/api/bot", tags=["bot"])
app.include_router(trades.router, prefix="/api/trades", tags=["trades"])
app.include_router(websocket.router, tags=["websocket"])
app.include_router(workspace_router, prefix="/api/workspace", tags=["workspace"])
app.include_router(workspace_trades_router, prefix="/api/workspace/trades", tags=["workspace-trades"])
app.include_router(strategies_router, prefix="/api/strategies", tags=["strategies"])
app.include_router(workspace_websocket_router, tags=["workspace-websocket"])


@app.get("/api/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
