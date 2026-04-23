"""Base class for all strategies."""
from __future__ import annotations

from abc import ABC, abstractmethod

from core.models.signal import Signal
from core.models.token import TokenCandidate


class BaseStrategy(ABC):
    name: str = "base"

    @abstractmethod
    async def evaluate(self, candidate: TokenCandidate) -> Signal | None:
        """
        Evaluate a candidate in WATCHING state.
        Returns an ENTER Signal if conditions are met, None otherwise.
        """
        ...

    @abstractmethod
    def is_ready(self, candidate: TokenCandidate) -> bool:
        """
        Quick check: does this candidate have enough data to evaluate?
        Called frequently — must be fast (no I/O).
        """
        ...
