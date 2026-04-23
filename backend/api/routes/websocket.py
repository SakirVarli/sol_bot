"""
WebSocket endpoint — single stream for logs + state updates.
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger

from api.broadcaster import broadcaster
from api.routes.bot import get_status
from api.routes.trades import get_trade_history

router = APIRouter()


@router.websocket("/ws/stream")
async def ws_stream(websocket: WebSocket):
    await broadcaster.connect(websocket)
    logger.debug(f"WS client connected ({len(broadcaster._clients)} total)")

    try:
        # Send current state immediately on connect
        state = await get_status()
        await websocket.send_json({"type": "state", "data": state})

        history = await get_trade_history(limit=50)
        await websocket.send_json({"type": "history", "data": history})

        # Keep connection alive — client sends pings, we just receive them
        while True:
            await websocket.receive_text()

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.debug(f"WS client error: {e}")
    finally:
        broadcaster.disconnect(websocket)
        logger.debug(f"WS client disconnected ({len(broadcaster._clients)} remaining)")
