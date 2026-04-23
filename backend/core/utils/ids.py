"""Unique ID generation."""
from __future__ import annotations

import uuid
import time


def new_id(prefix: str = "") -> str:
    """Generate a short unique ID with optional prefix."""
    uid = uuid.uuid4().hex[:12]
    if prefix:
        return f"{prefix}_{uid}"
    return uid


def event_id() -> str:
    return new_id("evt")


def position_id() -> str:
    return new_id("pos")


def signal_id() -> str:
    return new_id("sig")


def strategy_definition_id() -> str:
    return new_id("strdef")


def strategy_instance_id() -> str:
    return new_id("str")
