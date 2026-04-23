from __future__ import annotations

import time
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class TokenState(str, Enum):
    NEW = "NEW"
    FILTERING = "FILTERING"
    WATCHING = "WATCHING"
    READY = "READY"
    ENTERING = "ENTERING"
    OPEN = "OPEN"
    EXITING = "EXITING"
    CLOSED = "CLOSED"
    BLACKLISTED = "BLACKLISTED"
    REJECTED = "REJECTED"


# Valid state transitions
_TRANSITIONS: dict[TokenState, set[TokenState]] = {
    TokenState.NEW:        {TokenState.FILTERING, TokenState.REJECTED},
    TokenState.FILTERING:  {TokenState.WATCHING, TokenState.REJECTED, TokenState.BLACKLISTED},
    TokenState.WATCHING:   {TokenState.READY, TokenState.REJECTED},
    TokenState.READY:      {TokenState.ENTERING, TokenState.REJECTED},
    TokenState.ENTERING:   {TokenState.OPEN, TokenState.REJECTED},
    TokenState.OPEN:       {TokenState.EXITING, TokenState.BLACKLISTED},
    TokenState.EXITING:    {TokenState.CLOSED, TokenState.BLACKLISTED},
    TokenState.CLOSED:     set(),
    TokenState.BLACKLISTED: set(),
    TokenState.REJECTED:   set(),
}


class PricePoint(BaseModel):
    ts: float
    price: float
    volume_usd: float = 0.0


class TokenCandidate(BaseModel):
    # Identity
    mint: str
    pool_address: Optional[str] = None
    symbol: Optional[str] = None
    name: Optional[str] = None
    source: str = "raydium"             # raydium | pumpfun | unknown

    # Timestamps
    first_seen_ts: float = Field(default_factory=time.time)
    filter_start_ts: Optional[float] = None
    watch_start_ts: Optional[float] = None
    entry_ts: Optional[float] = None

    # Filter results
    liquidity_usd: float = 0.0
    buy_route_ok: bool = False
    sell_route_ok: bool = False
    mint_authority_disabled: Optional[bool] = None
    freeze_authority_disabled: Optional[bool] = None
    top_holder_pct: Optional[float] = None   # % held by largest non-pool wallet
    suspicious_score: float = 0.0
    filter_notes: list[str] = Field(default_factory=list)

    # Watch phase market data
    initial_price: Optional[float] = None
    peak_price: Optional[float] = None
    current_price: Optional[float] = None
    price_history: list[PricePoint] = Field(default_factory=list)
    swap_count: int = 0
    unique_buyers: int = 0
    volume_usd: float = 0.0

    # State
    state: TokenState = TokenState.NEW
    reject_reason: Optional[str] = None

    # -------------------------------------------------------
    # State machine
    # -------------------------------------------------------

    def transition(self, new_state: TokenState) -> None:
        allowed = _TRANSITIONS.get(self.state, set())
        if new_state not in allowed:
            raise ValueError(
                f"Invalid transition {self.state} → {new_state} for mint {self.mint}"
            )
        self.state = new_state

    def reject(self, reason: str) -> None:
        self.reject_reason = reason
        self.state = TokenState.REJECTED

    def blacklist(self, reason: str) -> None:
        self.reject_reason = reason
        self.state = TokenState.BLACKLISTED

    # -------------------------------------------------------
    # Helpers
    # -------------------------------------------------------

    def age_seconds(self) -> float:
        return time.time() - self.first_seen_ts

    def watch_elapsed_seconds(self) -> float:
        if self.watch_start_ts is None:
            return 0.0
        return time.time() - self.watch_start_ts

    def record_price(self, price: float, volume_usd: float = 0.0) -> None:
        pt = PricePoint(ts=time.time(), price=price, volume_usd=volume_usd)
        self.price_history.append(pt)
        self.current_price = price
        if self.initial_price is None:
            self.initial_price = price
        if self.peak_price is None or price > self.peak_price:
            self.peak_price = price

    def price_change_pct(self) -> Optional[float]:
        if self.initial_price and self.initial_price > 0 and self.current_price:
            return ((self.current_price - self.initial_price) / self.initial_price) * 100
        return None

    def retrace_from_peak_pct(self) -> Optional[float]:
        if self.peak_price and self.peak_price > 0 and self.current_price:
            return ((self.peak_price - self.current_price) / self.peak_price) * 100
        return None

    def __repr__(self) -> str:
        return f"TokenCandidate(mint={self.mint[:8]}…, state={self.state}, liq=${self.liquidity_usd:.0f})"
