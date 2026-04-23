from __future__ import annotations

import time
from typing import Any, Optional
from pydantic import BaseModel, Field


class TradeEvent(BaseModel):
    event_id: str
    mint: str
    event_type: str     # DETECTED | FILTER_PASS | FILTER_REJECT | BUY_SENT | BUY_FILLED |
                        # BUY_FAILED | SELL_SENT | SELL_FILLED | SELL_FAILED |
                        # PRICE_UPDATE | TP1_HIT | STOP_HIT | TIME_STOP | POSITION_CLOSED
    ts: float = Field(default_factory=time.time)
    details: dict[str, Any] = Field(default_factory=dict)
    position_id: Optional[str] = None
    tx_signature: Optional[str] = None

    # Key metrics at time of event (for replay and analysis)
    price: Optional[float] = None
    liquidity_usd: Optional[float] = None
    pnl_sol: Optional[float] = None
    pnl_pct: Optional[float] = None


# Convenience constructors

def detected_event(event_id: str, mint: str, source: str, pool: str, liq_usd: float) -> TradeEvent:
    return TradeEvent(
        event_id=event_id,
        mint=mint,
        event_type="DETECTED",
        details={"source": source, "pool": pool},
        liquidity_usd=liq_usd,
    )


def filter_event(event_id: str, mint: str, passed: bool, reason: str, score: float) -> TradeEvent:
    return TradeEvent(
        event_id=event_id,
        mint=mint,
        event_type="FILTER_PASS" if passed else "FILTER_REJECT",
        details={"reason": reason, "score": score},
    )


def position_closed_event(
    event_id: str,
    mint: str,
    position_id: str,
    exit_reason: str,
    pnl_sol: float,
    pnl_pct: float,
    hold_seconds: float,
) -> TradeEvent:
    return TradeEvent(
        event_id=event_id,
        mint=mint,
        event_type="POSITION_CLOSED",
        position_id=position_id,
        pnl_sol=pnl_sol,
        pnl_pct=pnl_pct,
        details={"exit_reason": exit_reason, "hold_seconds": hold_seconds},
    )
