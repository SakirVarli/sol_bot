"""Shared math helpers for price and risk calculations."""
from __future__ import annotations

from typing import Optional


def pct_change(old: float, new: float) -> float:
    """Percentage change from old to new."""
    if old == 0:
        return 0.0
    return ((new - old) / old) * 100


def pct_from_peak(peak: float, current: float) -> float:
    """How far (%) current is below peak."""
    if peak == 0:
        return 0.0
    return ((peak - current) / peak) * 100


def bps_to_pct(bps: int) -> float:
    return bps / 100.0


def pct_to_bps(pct: float) -> int:
    return int(pct * 100)


def sol_to_lamports(sol: float) -> int:
    return int(sol * 1_000_000_000)


def lamports_to_sol(lamports: int) -> float:
    return lamports / 1_000_000_000


def price_impact_pct(amount_in: float, amount_out: float, expected_out: float) -> float:
    """Estimate price impact as % deviation from expected."""
    if expected_out == 0:
        return 0.0
    return ((expected_out - amount_out) / expected_out) * 100


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def trailing_stop_price(peak_price: float, trail_pct: float) -> float:
    """Trailing stop = peak * (1 - trail_pct/100)."""
    return peak_price * (1 - trail_pct / 100)


def take_profit_price(entry_price: float, tp_pct: float) -> float:
    return entry_price * (1 + tp_pct / 100)


def stop_loss_price(entry_price: float, sl_pct: float) -> float:
    """sl_pct should be negative (e.g. -15.0 for -15%)."""
    return entry_price * (1 + sl_pct / 100)
