"""
Central broadcast hub for WebSocket clients.

Two channels:
  - Logs: real-time log entries from loguru sink
  - State: periodic bot state snapshots (positions, pipeline, stats)

Architecture:
  loguru → sink() → _pending deque → run() → all WS clients
  state_loop()                      → broadcast_state() → all WS clients
"""
from __future__ import annotations

import asyncio
from collections import deque
from typing import TYPE_CHECKING

from fastapi import WebSocket

if TYPE_CHECKING:
    pass


class Broadcaster:
    def __init__(self, log_buffer_size: int = 500) -> None:
        self._clients: list[WebSocket] = []
        self._log_buffer: deque[dict] = deque(maxlen=log_buffer_size)
        self._pending_logs: deque[dict] = deque()
        self._running = False

    # ── Loguru sink ───────────────────────────────────────────────────────────

    def loguru_sink(self, message) -> None:
        """Synchronous loguru sink — safe to call from any thread."""
        record = message.record
        entry = {
            "level": record["level"].name,
            "message": record["message"],
            "ts": record["time"].timestamp(),
            "module": record["module"],
        }
        self._log_buffer.append(entry)
        self._pending_logs.append(entry)

    # ── Client management ─────────────────────────────────────────────────────

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._clients.append(ws)
        # Replay buffered logs to new client
        for entry in list(self._log_buffer):
            try:
                await ws.send_json({"type": "log", "data": entry})
            except Exception:
                break

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self._clients:
            self._clients.remove(ws)

    # ── Broadcast methods ─────────────────────────────────────────────────────

    async def broadcast_state(self, state: dict) -> None:
        await self._broadcast({"type": "state", "data": state})

    async def broadcast_history(self, trades: list) -> None:
        await self._broadcast({"type": "history", "data": trades})

    async def _broadcast(self, msg: dict) -> None:
        dead: list[WebSocket] = []
        for ws in self._clients:
            try:
                await ws.send_json(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._clients.remove(ws)

    # ── Background log drain loop ─────────────────────────────────────────────

    async def run(self) -> None:
        """Drain pending logs every 100ms and broadcast to all clients."""
        self._running = True
        while self._running:
            await asyncio.sleep(0.1)
            while self._pending_logs:
                entry = self._pending_logs.popleft()
                await self._broadcast({"type": "log", "data": entry})

    def stop(self) -> None:
        self._running = False


# Singleton — imported by routes and bot_runner
broadcaster = Broadcaster()
