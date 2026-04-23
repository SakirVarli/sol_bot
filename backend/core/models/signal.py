from __future__ import annotations

import time
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class SignalType(str, Enum):
    ENTER = "ENTER"
    EXIT_PARTIAL = "EXIT_PARTIAL"
    EXIT_FULL = "EXIT_FULL"


class Signal(BaseModel):
    signal_id: str
    signal_type: SignalType
    mint: str
    ts: float = Field(default_factory=time.time)
    strategy: str = ""
    strategy_id: str = ""
    strategy_name: str = ""
    mode: str = "paper"
    ledger_type: str = "paper"
    rule_version: int = 1
    entry_reason: str = ""

    # Entry params
    suggested_size_sol: float = 0.0
    suggested_slippage_bps: int = 300

    # Exit params
    exit_fraction: float = 1.0          # 1.0 = full exit
    exit_reason: str = ""

    # Context
    token_score: float = 0.0
    liquidity_usd: float = 0.0
    confidence: float = 1.0
    notes: str = ""
