from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger

from api.broadcaster import broadcaster
from api.routes.workspace import get_workspace_status
from api.routes.workspace_trades import get_trade_history

router = APIRouter()


@router.websocket("/ws/workspace")
async def ws_workspace(websocket: WebSocket):
    await broadcaster.connect(websocket)
    logger.debug(f"WS client connected ({len(broadcaster._clients)} total)")
    try:
        await websocket.send_json({"type": "state", "data": await get_workspace_status()})
        await websocket.send_json({"type": "history", "data": await get_trade_history(limit=100)})
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.debug(f"WS client error: {exc}")
    finally:
        broadcaster.disconnect(websocket)
