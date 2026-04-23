"""
Shared application state — singleton populated by bot_runner, read by API routes.
"""
from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from core.discovery.launch_detector import LaunchDetector
    from core.portfolio.position_manager import PositionManager
    from core.storage.trade_log import TradeLog


class AppState:
    # Bot lifecycle
    running: bool = False
    mode: str = "paper"
    bot_task: Optional[asyncio.Task] = None
    start_time: Optional[float] = None
    stop_reason: Optional[str] = None

    # Component references (set by bot_runner on start, cleared on stop)
    detector: Optional["LaunchDetector"] = None
    position_mgr: Optional["PositionManager"] = None
    trade_log: Optional["TradeLog"] = None

    # Config snapshot
    config: dict = {}

    # Paper balance tracking
    paper_balance_sol: float = 10.0
    paper_initial_sol: float = 10.0

    def uptime_seconds(self) -> float:
        if self.start_time is None:
            return 0.0
        return time.time() - self.start_time

    def to_dict(self) -> dict:
        return {
            "running": self.running,
            "mode": self.mode,
            "uptime_seconds": self.uptime_seconds(),
            "stop_reason": self.stop_reason,
        }


# Singleton
app_state = AppState()
