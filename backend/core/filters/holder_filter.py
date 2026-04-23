"""
Checks holder concentration.

If the top holder (excluding the pool vault) holds > threshold% of supply,
the token is likely a rug setup.
"""
from __future__ import annotations

from loguru import logger

from core.models.token import TokenCandidate
from core.utils.rpc_client import SolanaRPC


class HolderFilter:
    def __init__(
        self,
        rpc: SolanaRPC,
        max_top_holder_pct: float = 30.0,
        pool_address: str | None = None,
    ) -> None:
        self._rpc = rpc
        self._max_pct = max_top_holder_pct

    async def check(self, candidate: TokenCandidate, pool_address: str | None = None) -> bool:
        try:
            supply_info = await self._rpc.get_token_supply(candidate.mint)
            if supply_info is None:
                candidate.reject("supply_fetch_failed")
                return False

            total_supply = float(supply_info.get("uiAmount", 0))
            if total_supply <= 0:
                candidate.reject("zero_supply")
                return False

            largest = await self._rpc.get_token_largest_accounts(candidate.mint)
            if not largest:
                candidate.reject("holder_fetch_failed")
                return False

            # Exclude pool vault if we know it
            pool = pool_address or candidate.pool_address
            filtered = [
                h for h in largest
                if h.get("address") != pool
            ]

            if not filtered:
                return True

            top_amount = float(filtered[0].get("uiAmount", 0))
            top_pct = (top_amount / total_supply) * 100 if total_supply > 0 else 0

            candidate.top_holder_pct = top_pct

            if top_pct > self._max_pct:
                candidate.filter_notes.append(f"top_holder_{top_pct:.1f}pct")
                candidate.suspicious_score += min(50, top_pct)
                candidate.reject(f"holder_concentration: {top_pct:.1f}% > {self._max_pct}%")
                return False

            # Warn if close to threshold
            if top_pct > self._max_pct * 0.7:
                candidate.filter_notes.append(f"high_concentration_{top_pct:.1f}pct")
                candidate.suspicious_score += 10

            return True

        except Exception as e:
            logger.error(f"HolderFilter error for {candidate.mint[:8]}…: {e}")
            # Don't reject on error — be permissive, note it
            candidate.filter_notes.append("holder_check_failed")
            return True
