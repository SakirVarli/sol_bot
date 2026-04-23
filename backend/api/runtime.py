from __future__ import annotations

import asyncio
import time
from typing import Optional

from core.engine.supervisor import EngineSupervisor


class RuntimeState:
    running: bool = False
    bot_task: Optional[asyncio.Task] = None
    start_time: Optional[float] = None
    stop_reason: Optional[str] = None
    config: dict = {}
    supervisor: Optional[EngineSupervisor] = None

    def uptime_seconds(self) -> float:
        if self.start_time is None:
            return 0.0
        return time.time() - self.start_time


runtime_state = RuntimeState()
