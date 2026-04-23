"""
Checks mint authority and freeze authority status.

Tokens with live mint authority can be inflated arbitrarily.
Tokens with live freeze authority can have wallets frozen (prevents selling).

Both are hard rejects for our strategy.
"""
from __future__ import annotations

from loguru import logger

from core.models.token import TokenCandidate
from core.utils.rpc_client import SolanaRPC, parse_mint_account


class AuthorityFilter:
    def __init__(self, rpc: SolanaRPC) -> None:
        self._rpc = rpc

    async def check(self, candidate: TokenCandidate) -> bool:
        """Returns True if the candidate passes authority checks."""
        try:
            info = await self._rpc.get_account_info(candidate.mint, encoding="base64")
            if info is None:
                candidate.reject("mint_account_not_found")
                return False

            data_list = info.get("data")
            if not data_list or not isinstance(data_list, list):
                candidate.reject("mint_data_missing")
                return False

            parsed = parse_mint_account(data_list[0])
            if not parsed:
                candidate.reject("mint_parse_failed")
                return False

            if not parsed.get("is_initialized"):
                candidate.reject("mint_not_initialized")
                return False

            has_mint_auth = parsed.get("has_mint_authority", True)
            has_freeze_auth = parsed.get("has_freeze_authority", True)

            # Update candidate
            candidate.mint_authority_disabled = not has_mint_auth
            candidate.freeze_authority_disabled = not has_freeze_auth

            if has_mint_auth:
                candidate.filter_notes.append("live_mint_authority")
                candidate.suspicious_score += 40
                logger.debug(f"{candidate.mint[:8]}… has live mint authority")

            if has_freeze_auth:
                candidate.filter_notes.append("live_freeze_authority")
                candidate.suspicious_score += 30
                logger.debug(f"{candidate.mint[:8]}… has live freeze authority")

            # Hard reject: either authority present
            if has_mint_auth or has_freeze_auth:
                candidate.reject(
                    f"authority_risk: mint={has_mint_auth} freeze={has_freeze_auth}"
                )
                return False

            return True

        except Exception as e:
            logger.error(f"AuthorityFilter error for {candidate.mint[:8]}…: {e}")
            candidate.reject(f"authority_check_error: {e}")
            return False
