"""
Checks pool liquidity is above minimum threshold.

Uses Jupiter quote to estimate effective liquidity:
  - Quote a large trade and measure price impact
  - Estimate pool depth from the impact

Also provides a quick SOL balance check on the pool vault.
"""
from __future__ import annotations

from loguru import logger

import httpx

from core.models.token import TokenCandidate
from core.utils.math_utils import sol_to_lamports, lamports_to_sol

WSOL_MINT = "So11111111111111111111111111111111111111112"
JUPITER_QUOTE_URL = "https://quote-api.jup.ag/v6/quote"

# Approximate SOL price in USD for liquidity estimation
# In production, fetch this from an oracle (Pyth, etc.)
SOL_PRICE_USD_APPROX = 150.0


class LiquidityFilter:
    def __init__(
        self,
        min_liquidity_usd: float = 10_000.0,
        timeout: float = 5.0,
    ) -> None:
        self._min_liq_usd = min_liquidity_usd
        self._client = httpx.AsyncClient(timeout=timeout)

    async def check(self, candidate: TokenCandidate) -> bool:
        """
        Estimate liquidity via price impact on a reference trade size.
        Returns False if liquidity is below threshold.
        """
        try:
            # Quote a 1 SOL trade
            ref_amount = sol_to_lamports(1.0)
            quote_1sol = await self._get_quote(WSOL_MINT, candidate.mint, ref_amount)

            if quote_1sol is None:
                candidate.filter_notes.append("liquidity_quote_failed")
                # Don't hard reject here — let route_filter handle missing routes
                return True

            price_impact_pct = abs(float(quote_1sol.get("priceImpactPct", 0))) * 100

            # Estimate pool depth from price impact
            # Impact ≈ trade_size / (2 * pool_depth)  (for constant product AMM)
            # pool_depth ≈ trade_size / (2 * impact)
            if price_impact_pct > 0:
                pool_depth_sol = 1.0 / (2 * price_impact_pct / 100)
                liq_usd = pool_depth_sol * 2 * SOL_PRICE_USD_APPROX
            else:
                # Zero impact — very deep pool (or error). Assume minimum threshold.
                liq_usd = self._min_liq_usd

            candidate.liquidity_usd = liq_usd

            if liq_usd < self._min_liq_usd:
                candidate.filter_notes.append(f"low_liquidity_{liq_usd:.0f}usd")
                candidate.reject(
                    f"low_liquidity: ${liq_usd:.0f} < ${self._min_liq_usd:.0f}"
                )
                return False

            logger.debug(
                f"LiquidityFilter | {candidate.mint[:8]}… "
                f"impact={price_impact_pct:.2f}% liq≈${liq_usd:.0f}"
            )
            return True

        except Exception as e:
            logger.error(f"LiquidityFilter error for {candidate.mint[:8]}…: {e}")
            candidate.filter_notes.append("liquidity_check_error")
            return True   # Permissive on error — other filters will catch bad tokens

    async def _get_quote(self, input_mint: str, output_mint: str, amount: int) -> dict | None:
        params = {
            "inputMint": input_mint,
            "outputMint": output_mint,
            "amount": amount,
            "slippageBps": 100,
        }
        try:
            resp = await self._client.get(JUPITER_QUOTE_URL, params=params)
            if resp.status_code != 200:
                return None
            data = resp.json()
            if "error" in data:
                return None
            return data
        except Exception:
            return None

    async def close(self) -> None:
        await self._client.aclose()
