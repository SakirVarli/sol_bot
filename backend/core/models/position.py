from __future__ import annotations

import time
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class PositionStatus(str, Enum):
    PENDING = "PENDING"       # Buy sent, not confirmed
    OPEN = "OPEN"             # Buy confirmed
    PARTIAL_EXIT = "PARTIAL_EXIT"  # TP1 hit, trailing rest
    CLOSING = "CLOSING"       # Sell sent
    CLOSED = "CLOSED"         # Fully closed


class ExitReason(str, Enum):
    TP1 = "TP1"
    TP2 = "TP2"
    TRAILING_STOP = "TRAILING_STOP"
    HARD_STOP = "HARD_STOP"
    TIME_STOP = "TIME_STOP"
    LIQUIDITY_COLLAPSE = "LIQUIDITY_COLLAPSE"
    MANUAL = "MANUAL"
    EMERGENCY = "EMERGENCY"


class PartialFill(BaseModel):
    ts: float
    quantity: float
    price: float
    reason: str   # tp1, trailing_stop, hard_stop, time_stop, etc.


class Position(BaseModel):
    # Identity
    position_id: str
    mint: str
    pool_address: Optional[str] = None
    mode: str = "paper"       # paper | live

    # Entry
    entry_ts: float = Field(default_factory=time.time)
    entry_price: float = 0.0
    entry_tx: Optional[str] = None
    quantity: float = 0.0           # Token quantity held
    cost_sol: float = 0.0           # SOL spent on entry
    cost_usd: float = 0.0

    # Live tracking
    current_price: float = 0.0
    highest_price: float = 0.0
    last_update_ts: float = Field(default_factory=time.time)

    # P&L
    unrealized_pnl_sol: float = 0.0
    realized_pnl_sol: float = 0.0

    # Exit config (copied from strategy at entry time)
    tp1_price: float = 0.0          # Sell tp1_fraction at this price
    tp1_fraction: float = 0.5
    tp1_triggered: bool = False
    trailing_stop_pct: float = 25.0
    hard_stop_price: float = 0.0
    time_stop_ts: float = 0.0       # Unix ts when we force-exit

    # Fills
    exit_fills: list[PartialFill] = Field(default_factory=list)

    # Status
    status: PositionStatus = PositionStatus.PENDING
    exit_reason: Optional[ExitReason] = None
    close_ts: Optional[float] = None

    # -------------------------------------------------------
    # Computed helpers
    # -------------------------------------------------------

    def update_price(self, price: float) -> None:
        self.current_price = price
        self.last_update_ts = time.time()
        if price > self.highest_price:
            self.highest_price = price
        if self.cost_sol > 0:
            current_value = self.quantity * price
            self.unrealized_pnl_sol = current_value - self.cost_sol

    def trailing_stop_price(self) -> float:
        """Current trailing stop price based on highest seen price."""
        if self.highest_price <= 0:
            return self.hard_stop_price
        return self.highest_price * (1 - self.trailing_stop_pct / 100)

    def hold_seconds(self) -> float:
        return time.time() - self.entry_ts

    def pnl_pct(self) -> float:
        if self.cost_sol <= 0:
            return 0.0
        total_realized = self.realized_pnl_sol
        total_unrealized = self.unrealized_pnl_sol
        return ((total_realized + total_unrealized) / self.cost_sol) * 100

    def is_past_time_stop(self) -> bool:
        return self.time_stop_ts > 0 and time.time() >= self.time_stop_ts

    def __repr__(self) -> str:
        return (
            f"Position(mint={self.mint[:8]}…, status={self.status}, "
            f"pnl={self.pnl_pct():.1f}%, hold={self.hold_seconds():.0f}s)"
        )
