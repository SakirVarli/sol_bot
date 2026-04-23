from __future__ import annotations

import math
from collections import defaultdict

from core.models.candle import Candle


class CandleService:
    def __init__(self, history_limit: int = 256) -> None:
        self._history_limit = history_limit
        self._active: dict[tuple[str, int], Candle] = {}
        self._history: dict[tuple[str, int], list[Candle]] = defaultdict(list)
        self._timeframes: set[int] = set()

    def register_timeframe(self, timeframe_seconds: int) -> None:
        self._timeframes.add(max(1, timeframe_seconds))

    def add_tick(
        self,
        mint: str,
        price: float,
        ts: float,
        volume_usd: float = 0.0,
    ) -> list[Candle]:
        closed: list[Candle] = []
        for timeframe in sorted(self._timeframes):
            key = (mint, timeframe)
            bucket_start = math.floor(ts / timeframe) * timeframe
            candle = self._active.get(key)
            if candle is None:
                self._active[key] = Candle(
                    mint=mint,
                    timeframe_seconds=timeframe,
                    open_ts=bucket_start,
                    close_ts=bucket_start + timeframe,
                    open=price,
                    high=price,
                    low=price,
                    close=price,
                    volume_usd=volume_usd,
                )
                continue

            if bucket_start >= candle.close_ts:
                closed.append(candle.model_copy(deep=True))
                history = self._history[key]
                history.append(candle.model_copy(deep=True))
                if len(history) > self._history_limit:
                    del history[:-self._history_limit]
                self._active[key] = Candle(
                    mint=mint,
                    timeframe_seconds=timeframe,
                    open_ts=bucket_start,
                    close_ts=bucket_start + timeframe,
                    open=price,
                    high=price,
                    low=price,
                    close=price,
                    volume_usd=volume_usd,
                )
                continue

            candle.close = price
            candle.high = max(candle.high, price)
            candle.low = min(candle.low, price)
            candle.volume_usd += volume_usd
        return closed

    def get_candles(self, mint: str, timeframe_seconds: int) -> list[Candle]:
        return list(self._history.get((mint, timeframe_seconds), []))
