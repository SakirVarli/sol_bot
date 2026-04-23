from __future__ import annotations

import asyncio
from typing import Callable

import httpx
from loguru import logger

JUPITER_PRICE_URL = "https://api.jup.ag/price/v2"
WSOL_MINT = "So11111111111111111111111111111111111111112"


class SwapListener:
    def __init__(self, poll_interval_seconds: float = 2.0) -> None:
        self._poll_interval = poll_interval_seconds
        self._watched: dict[str, list[Callable[[str, float], None]]] = {}
        self._client = httpx.AsyncClient(timeout=5.0)
        self._running = False

    def watch(self, mint: str, on_price_update: Callable[[str, float], None]) -> None:
        callbacks = self._watched.setdefault(mint, [])
        if on_price_update not in callbacks:
            callbacks.append(on_price_update)
        logger.debug(f"SwapListener watching {mint[:8]}...")

    def unwatch(self, mint: str, on_price_update: Callable[[str, float], None] | None = None) -> None:
        if on_price_update is None:
            self._watched.pop(mint, None)
        else:
            callbacks = self._watched.get(mint, [])
            self._watched[mint] = [cb for cb in callbacks if cb != on_price_update]
            if not self._watched[mint]:
                self._watched.pop(mint, None)
        logger.debug(f"SwapListener unwatching {mint[:8]}...")

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
        try:
            resp = await self._client.get(
                JUPITER_PRICE_URL,
                params={"ids": ",".join(mints), "vsToken": WSOL_MINT},
            )
            resp.raise_for_status()
            data = resp.json().get("data", {})
            for mint in mints:
                info = data.get(mint)
                if info is None:
                    continue
                price = float(info.get("price", 0))
                if price <= 0:
                    continue
                for callback in list(self._watched.get(mint, [])):
                    try:
                        callback(mint, price)
                    except Exception as exc:
                        logger.error(f"SwapListener callback error for {mint[:8]}...: {exc}")
        except Exception as exc:
            logger.warning(f"SwapListener price poll failed: {exc}")

    async def close(self) -> None:
        self._running = False
        await self._client.aclose()

    def get_watched_mints(self) -> list[str]:
        return list(self._watched.keys())
