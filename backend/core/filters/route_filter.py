"""
Checks that buy and sell routes exist via Jupiter.

A token with no sell route is a honey pot — you can buy but not sell.
We check both directions before ever touching a token.
"""
from __future__ import annotations

from loguru import logger

import httpx

from core.models.token import TokenCandidate
from core.utils.math_utils import sol_to_lamports

WSOL_MINT = "So11111111111111111111111111111111111111112"
JUPITER_QUOTE_URL = "https://quote-api.jup.ag/v6/quote"


class RouteFilter:
    def __init__(
        self,
        check_amount_sol: float = 0.1,
        max_slippage_bps: int = 500,
        timeout: float = 5.0,
    ) -> None:
        self._amount_lamports = sol_to_lamports(check_amount_sol)
        self._max_slippage_bps = max_slippage_bps
        self._client = httpx.AsyncClient(timeout=timeout)

    async def check(self, candidate: TokenCandidate) -> bool:
        """Check both buy and sell routes exist. Updates candidate in-place."""
        buy_ok = await self._check_route(
            input_mint=WSOL_MINT,
            output_mint=candidate.mint,
            label="buy",
        )
        candidate.buy_route_ok = buy_ok

        if not buy_ok:
            candidate.reject("no_buy_route")
            return False

        # For sell route, use a small token amount
        # We approximate by checking quote in reverse
        # Use 1% of token supply as proxy — simplified: just check route exists
        sell_ok = await self._check_route(
            input_mint=candidate.mint,
            output_mint=WSOL_MINT,
            amount=1_000_000,   # 1M base units (adjust per decimals ideally)
            label="sell",
        )
        candidate.sell_route_ok = sell_ok

        if not sell_ok:
            candidate.filter_notes.append("no_sell_route")
            candidate.suspicious_score += 60
            candidate.reject("no_sell_route")
            return False

        return True

    async def _check_route(
        self,
        input_mint: str,
        output_mint: str,
        amount: int | None = None,
        label: str = "",
    ) -> bool:
        params = {
            "inputMint": input_mint,
            "outputMint": output_mint,
            "amount": amount or self._amount_lamports,
            "slippageBps": self._max_slippage_bps,
        }
        try:
            resp = await self._client.get(JUPITER_QUOTE_URL, params=params)
            if resp.status_code == 200:
                data = resp.json()
                # Jupiter returns an error field if no route found
                if "error" in data:
                    logger.debug(f"RouteFilter {label}: no route — {data['error']}")
                    return False
                return bool(data.get("outAmount"))
            elif resp.status_code == 400:
                logger.debug(f"RouteFilter {label}: 400 — no route available")
                return False
            else:
                logger.warning(f"RouteFilter {label}: HTTP {resp.status_code}")
                return False
        except Exception as e:
            logger.error(f"RouteFilter {label} error: {e}")
            return False

    async def get_quote(
        self,
        input_mint: str,
        output_mint: str,
        amount_lamports: int,
        slippage_bps: int = 300,
    ) -> dict | None:
        """Get a full quote for execution."""
        params = {
            "inputMint": input_mint,
            "outputMint": output_mint,
            "amount": amount_lamports,
            "slippageBps": slippage_bps,
            "onlyDirectRoutes": False,
        }
        try:
            resp = await self._client.get(JUPITER_QUOTE_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
            if "error" in data:
                return None
            return data
        except Exception as e:
            logger.error(f"RouteFilter get_quote error: {e}")
            return None

    async def close(self) -> None:
        await self._client.aclose()
