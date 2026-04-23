"""Centralized time utilities. Allows easy mocking in tests/replay."""
from __future__ import annotations

import time as _time
from typing import Optional


class Clock:
    """Can be overridden in replay/test mode to fast-forward time."""

    _override_ts: Optional[float] = None

    @classmethod
    def now(cls) -> float:
        if cls._override_ts is not None:
            return cls._override_ts
        return _time.time()

    @classmethod
    def set(cls, ts: float) -> None:
        cls._override_ts = ts

    @classmethod
    def reset(cls) -> None:
        cls._override_ts = None

    @classmethod
    def is_mocked(cls) -> bool:
        return cls._override_ts is not None


def now() -> float:
    return Clock.now()


def elapsed_since(ts: float) -> float:
    return Clock.now() - ts
