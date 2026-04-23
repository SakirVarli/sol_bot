"""
Strategy: First-Minute Pullback Breakout

Logic:
  1. Token launches with initial price spike (>= min_spike_pct)
  2. Price pulls back from peak (>= min_retrace_pct but <= max_retrace_pct)
  3. Volume and buyer count remain healthy
  4. Price breaks back above the pullback high (breakout confirmation)
  → ENTER

This is a momentum strategy that catches the first continuation move
after the launch spike settles.
"""
from __future__ import annotations

import time
from typing import Optional

from loguru import logger

from core.models.signal import Signal, SignalType
from core.models.token import TokenCandidate
from core.strategy.base_strategy import BaseStrategy
from core.utils.ids import signal_id
from core.utils.math_utils import pct_change, pct_from_peak


class FirstPullbackStrategy(BaseStrategy):
    name = "first_pullback"

    def __init__(self, config: dict, trade_size_sol: float = 0.1) -> None:
        fp = config.get("strategy", {}).get("first_pullback", {})
        self._watch_window = fp.get("watch_window_seconds", 90)
        self._min_spike_pct = fp.get("min_initial_spike_pct", 20.0)
        self._max_retrace_pct = fp.get("max_retrace_pct", 50.0)
        self._min_volume_usd = fp.get("min_volume_usd", 5000.0)
        self._min_buyers = fp.get("min_unique_buyers", 10)
        self._trade_size_sol = trade_size_sol

        # Internal state per token
        self._pullback_lows: dict[str, float] = {}     # mint → lowest price seen after spike
        self._spike_confirmed: dict[str, bool] = {}
        self._pullback_confirmed: dict[str, bool] = {}

    def is_ready(self, candidate: TokenCandidate) -> bool:
        return len(candidate.price_history) >= 3

    async def evaluate(self, candidate: TokenCandidate) -> Optional[Signal]:
        mint = candidate.mint

        if not candidate.initial_price or not candidate.current_price or not candidate.peak_price:
            return None

        initial = candidate.initial_price
        peak = candidate.peak_price
        current = candidate.current_price

        # Step 1: Confirm initial spike
        spike_pct = pct_change(initial, peak)
        if spike_pct < self._min_spike_pct:
            return None   # No meaningful spike yet

        self._spike_confirmed[mint] = True

        # Step 2: Confirm pullback
        retrace_from_peak = pct_from_peak(peak, current)
        if retrace_from_peak < 10:
            return None   # Not pulled back enough yet

        if retrace_from_peak > self._max_retrace_pct:
            # Pullback too deep — treat as collapse, not normal retrace
            logger.debug(
                f"{mint[:8]}… pullback too deep: {retrace_from_peak:.1f}% > {self._max_retrace_pct:.1f}%"
            )
            return None

        # Track the lowest point during pullback
        low = self._pullback_lows.get(mint, current)
        if current < low:
            self._pullback_lows[mint] = current
            self._pullback_confirmed[mint] = True

        pullback_low = self._pullback_lows.get(mint)
        if not pullback_low:
            return None

        # Step 3: Breakout confirmation
        # Price must have recovered from the pullback low
        recovery_pct = pct_change(pullback_low, current)
        if recovery_pct < 5.0:
            return None   # Not broken out yet

        # Step 4: Volume check (approximated via swap count)
        if candidate.swap_count < 5:
            return None

        # Step 5: Time check — must still be within watch window
        if candidate.watch_elapsed_seconds() > self._watch_window:
            return None

        logger.info(
            f"FirstPullback ENTRY SIGNAL | {mint[:8]}… "
            f"spike={spike_pct:.1f}% retrace={retrace_from_peak:.1f}% recovery={recovery_pct:.1f}%"
        )

        return Signal(
            signal_id=signal_id(),
            signal_type=SignalType.ENTER,
            mint=mint,
            strategy=self.name,
            suggested_size_sol=self._trade_size_sol,
            suggested_slippage_bps=300,
            liquidity_usd=candidate.liquidity_usd,
            token_score=candidate.suspicious_score,
            notes=(
                f"spike={spike_pct:.1f}% "
                f"retrace={retrace_from_peak:.1f}% "
                f"recovery={recovery_pct:.1f}%"
            ),
        )

    def reset(self, mint: str) -> None:
        """Clean up state for a mint after entry or rejection."""
        self._pullback_lows.pop(mint, None)
        self._spike_confirmed.pop(mint, None)
        self._pullback_confirmed.pop(mint, None)
