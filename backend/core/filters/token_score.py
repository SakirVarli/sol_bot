"""
FilterPipeline: runs all filters in sequence.

Each filter either mutates the candidate (adding score/notes) or rejects it.
The pipeline stops at the first hard rejection.

suspicious_score accumulates across filters:
  0–20  : clean
  20–50 : watch carefully
  50+   : reject
"""
from __future__ import annotations

from loguru import logger

from core.filters.authority_filter import AuthorityFilter
from core.filters.holder_filter import HolderFilter
from core.filters.liquidity_filter import LiquidityFilter
from core.filters.route_filter import RouteFilter
from core.models.token import TokenCandidate, TokenState
from core.utils.rpc_client import SolanaRPC


class FilterPipeline:
    def __init__(
        self,
        rpc: SolanaRPC,
        settings: dict,
    ) -> None:
        f = settings.get("filters", {})

        self._liquidity = LiquidityFilter(
            min_liquidity_usd=f.get("min_liquidity_usd", 10_000),
        )
        self._authority = AuthorityFilter(rpc=rpc)
        self._holder = HolderFilter(
            rpc=rpc,
            max_top_holder_pct=f.get("max_top_holder_pct", 30.0),
        )
        self._route = RouteFilter(
            check_amount_sol=f.get("route_check_amount_sol", 0.1),
            max_slippage_bps=f.get("max_slippage_bps", 500),
        )
        self._max_score = f.get("max_suspicious_score", 50)

    async def run(self, candidate: TokenCandidate) -> bool:
        """
        Run all filters. Returns True if candidate passes all checks.
        Mutates candidate.state, candidate.reject_reason, candidate.suspicious_score.
        """
        # 1. Authority check (fast — single RPC call)
        if not await self._authority.check(candidate):
            return False

        # 2. Route check (confirms both buy and sell exist)
        if not await self._route.check(candidate):
            return False

        # 3. Liquidity check (estimates pool depth)
        if not await self._liquidity.check(candidate):
            return False

        # 4. Holder concentration
        if not await self._holder.check(candidate):
            return False

        # 5. Global score check
        if candidate.suspicious_score >= self._max_score:
            candidate.reject(
                f"suspicious_score_too_high: {candidate.suspicious_score}"
            )
            return False

        logger.info(
            f"FilterPipeline PASS | {candidate.mint[:8]}… "
            f"score={candidate.suspicious_score} "
            f"liq=${candidate.liquidity_usd:.0f} "
            f"notes={candidate.filter_notes}"
        )
        return True

    async def close(self) -> None:
        await self._liquidity.close()
        await self._route.close()
