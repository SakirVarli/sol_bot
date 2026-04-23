from __future__ import annotations

import asyncio
import time

from loguru import logger

from api.broadcaster import broadcaster
from api.runtime import runtime_state
from core.engine.supervisor import EngineSupervisor


async def run_workspace(config: dict | None = None) -> None:
    if config is None:
        config = runtime_state.config

    sink_id = logger.add(broadcaster.loguru_sink, level="DEBUG", format="{message}")
    supervisor = EngineSupervisor(config=config)
    runtime_state.supervisor = supervisor
    runtime_state.running = True
    runtime_state.start_time = time.time()
    runtime_state.stop_reason = None

    try:
        await supervisor.start()
        while supervisor.running:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        logger.info("Workspace task cancelled")
    finally:
        await supervisor.stop(reason=runtime_state.stop_reason or "stopped")
        runtime_state.supervisor = None
        runtime_state.running = False
        logger.remove(sink_id)
