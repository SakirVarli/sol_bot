from __future__ import annotations

from pydantic import BaseModel


class Candle(BaseModel):
    mint: str
    timeframe_seconds: int
    open_ts: float
    close_ts: float
    open: float
    high: float
    low: float
    close: float
    volume_usd: float = 0.0

    @property
    def color(self) -> str:
        if self.close > self.open:
            return "green"
        if self.close < self.open:
            return "red"
        return "doji"
