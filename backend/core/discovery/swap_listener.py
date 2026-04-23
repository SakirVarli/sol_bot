"""
Tracks swap activity for tokens currently in WATCHING state.

For each watched token, subscribes to account change notifications on the pool vaults
and uses Jupiter price API to estimate current price and volume.

This feeds price data into TokenCandidate.price_history so strategies can
make entry decisions based on price action (spike → pullback → breakout).
"""
from __future__ import annotations

import asyncio
import time
from typing import Callable, Optional

import httpx
from loguru import logger

JUPITER_PRICE_URL = "https://api.jup.ag/price/v2"
WSOL_MINT = "So11111111111111111111111111111111111111112"


class SwapListener:
    """
    Polls Jupiter price API for tokens under watch.
    Cheap, reliable, and sufficient for V1 (no need for raw log parsing of swaps).

    For production phase 2+, replace with logsSubscribe on the AMM for lower latency.
    """

    def __init__(
        self,
        poll_interval_seconds: float = 2.0,
    ) -> None:
        self._poll_interval = poll_interval_seconds
        self._watched: dict[str, Callable] = {}   # mint → callback(price, volume_usd)
        self._client = httpx.AsyncClient(timeout=5.0)
        self._running = False

    def watch(self, mint: str, on_price_update: Callable[[str, float], None]) -> None:
        """Start tracking price for a mint. Callback receives (mint, price)."""
        self._watched[mint] = on_price_update
        logger.debug(f"SwapListener watching {mint[:8]}…")

    def unwatch(self, mint: str) -> None:
        self._watched.pop(mint, None)
        logger.debug(f"SwapListener unwatching {mint[:8]}…")

    async def run(self) -> None:
        self._running = True
        logger.info("SwapListener started (Jupiter price polling)")
        while self._running:
            if self._watched:
                await self._poll_prices()
            await asyncio.sleep(self._poll_interval)

    async def _poll_prices(self) -> None:
        mints = list(self._watched.keys())
        if not mints:
            return

        # Jupiter price API accepts comma-separated mint IDs
        ids = ",".join(mints)
        try:
            resp = await self._client.get(
                JUPITER_PRICE_URL,
                params={"ids": ids, "vsToken": WSOL_MINT},
            )
            resp.raise_for_status()
            data = resp.json().get("data", {})

            for mint in mints:
                info = data.get(mint)
                if info is None:
                    continue
                price = float(info.get("price", 0))
                if price > 0:
                    callback = self._watched.get(mint)
                    if callback:
                        try:
                            callback(mint, price)
                        except Exception as e:
                            logger.error(f"SwapListener callback error for {mint[:8]}…: {e}")

        except Exception as e:
            logger.warning(f"SwapListener price poll failed: {e}")

    async def close(self) -> None:
        self._running = False
        await self._client.aclose()

    def get_watched_mints(self) -> list[str]:
        return list(self._watched.keys())
