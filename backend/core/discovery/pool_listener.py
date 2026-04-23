"""
Listens for new Raydium AMM v4 and Pump.fun pool creations via Solana WebSocket logs.

Flow:
  1. Subscribe to logsSubscribe for Raydium AMM v4 program
  2. On log notification, check if it's a new pool ("initialize2")
  3. Fetch the transaction to extract base_mint, quote_mint, pool_address
  4. Push a raw PoolEvent to the output queue
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Optional

from loguru import logger

from core.utils.rpc_client import SolanaRPC, WSOL_MINT, USDC_MINT

# Raydium AMM v4 program
RAYDIUM_AMM_V4 = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"

# Pump.fun program
PUMPFUN_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"

# Raydium initialize2 account indices (0-based in the instruction's account list)
# These are the standard indices for AMM v4 create pool
_RAY_BASE_MINT_IDX = 8
_RAY_QUOTE_MINT_IDX = 9
_RAY_POOL_IDX = 4

# Quote mints we accept
ACCEPTED_QUOTE_MINTS = {WSOL_MINT, USDC_MINT}


@dataclass
class PoolEvent:
    mint: str               # Base token mint
    pool_address: str
    quote_mint: str
    source: str             # "raydium" | "pumpfun"
    signature: str
    slot: int


class PoolListener:
    """
    Detects new liquidity pool creations and emits PoolEvent objects.
    """

    def __init__(
        self,
        rpc_http: str,
        rpc_ws: str,
        out_queue: asyncio.Queue,
        accepted_quote_mints: set[str] | None = None,
    ) -> None:
        self._rpc = SolanaRPC(rpc_http)
        self._rpc_ws = rpc_ws
        self._queue = out_queue
        self._accepted_quotes = accepted_quote_mints or ACCEPTED_QUOTE_MINTS
        self._seen_signatures: set[str] = set()   # dedup

    # ── Public API ────────────────────────────────────────────────────────────

    async def run(self) -> None:
        """Start listening. Reconnects automatically on failure."""
        logger.info("PoolListener starting…")
        while True:
            try:
                await self._listen()
            except Exception as e:
                logger.warning(f"PoolListener disconnected: {e}. Reconnecting in 3s…")
                await asyncio.sleep(3)

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _listen(self) -> None:
        import websockets

        async with websockets.connect(
            self._rpc_ws,
            ping_interval=20,
            max_size=10 * 1024 * 1024,
        ) as ws:
            logger.info(f"PoolListener connected to WebSocket")

            # Subscribe to Raydium AMM v4 logs
            sub_req = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "logsSubscribe",
                "params": [
                    {"mentions": [RAYDIUM_AMM_V4]},
                    {"commitment": "confirmed"},
                ],
            }
            await ws.send(json.dumps(sub_req))

            # Subscribe to Pump.fun logs
            pf_req = {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "logsSubscribe",
                "params": [
                    {"mentions": [PUMPFUN_PROGRAM]},
                    {"commitment": "confirmed"},
                ],
            }
            await ws.send(json.dumps(pf_req))

            raydium_sub_id: Optional[int] = None
            pumpfun_sub_id: Optional[int] = None

            async for raw in ws:
                msg = json.loads(raw)

                # Capture subscription IDs
                if "id" in msg and "result" in msg:
                    if msg["id"] == 1:
                        raydium_sub_id = msg["result"]
                        logger.info(f"Raydium logs subscribed (sub={raydium_sub_id})")
                    elif msg["id"] == 2:
                        pumpfun_sub_id = msg["result"]
                        logger.info(f"Pump.fun logs subscribed (sub={pumpfun_sub_id})")
                    continue

                if msg.get("method") != "logsNotification":
                    continue

                params = msg["params"]
                sub_id = params["subscription"]
                value = params["result"]["value"]

                # Skip failed transactions
                if value.get("err") is not None:
                    continue

                sig = value["signature"]
                logs: list[str] = value.get("logs", [])
                slot = params["result"]["context"]["slot"]

                # Dedup
                if sig in self._seen_signatures:
                    continue

                if sub_id == raydium_sub_id:
                    asyncio.create_task(
                        self._handle_raydium_log(sig, logs, slot)
                    )
                elif sub_id == pumpfun_sub_id:
                    asyncio.create_task(
                        self._handle_pumpfun_log(sig, logs, slot)
                    )

    async def _handle_raydium_log(self, sig: str, logs: list[str], slot: int) -> None:
        """Check if this is a new pool creation and extract mints."""
        # Look for "initialize2" in logs — that's the Raydium AMM pool init instruction
        is_init = any("initialize2" in log for log in logs)
        if not is_init:
            return

        self._seen_signatures.add(sig)
        logger.debug(f"Raydium initialize2 detected: {sig[:16]}…")

        try:
            tx = await self._rpc.get_transaction(sig)
            if tx is None:
                return

            accounts = self._extract_accounts(tx)
            if len(accounts) <= max(_RAY_BASE_MINT_IDX, _RAY_QUOTE_MINT_IDX, _RAY_POOL_IDX):
                return

            base_mint = accounts[_RAY_BASE_MINT_IDX]
            quote_mint = accounts[_RAY_QUOTE_MINT_IDX]
            pool_address = accounts[_RAY_POOL_IDX]

            if quote_mint not in self._accepted_quotes:
                logger.debug(f"Ignoring pool with quote mint {quote_mint[:8]}…")
                return

            event = PoolEvent(
                mint=base_mint,
                pool_address=pool_address,
                quote_mint=quote_mint,
                source="raydium",
                signature=sig,
                slot=slot,
            )
            await self._queue.put(event)
            logger.info(
                f"New Raydium pool | mint={base_mint[:8]}… pool={pool_address[:8]}…"
            )

        except Exception as e:
            logger.error(f"Error handling Raydium log {sig[:16]}…: {e}")

    async def _handle_pumpfun_log(self, sig: str, logs: list[str], slot: int) -> None:
        """
        Detect Pump.fun token creation.
        Pump.fun 'create' instruction log contains 'Program log: Instruction: Create'
        """
        is_create = any(
            "Instruction: Create" in log or "CreateEvent" in log
            for log in logs
        )
        if not is_create:
            return

        self._seen_signatures.add(sig)
        logger.debug(f"Pump.fun create detected: {sig[:16]}…")

        try:
            tx = await self._rpc.get_transaction(sig)
            if tx is None:
                return

            # For pump.fun, the mint is typically the first non-system account
            # that appears after the program in the instruction accounts.
            # We use a heuristic: find the first account that's not a known program.
            accounts = self._extract_accounts(tx)
            mint = self._find_pumpfun_mint(accounts)
            if mint is None:
                return

            # Pump.fun tokens use SOL as quote
            event = PoolEvent(
                mint=mint,
                pool_address="",          # No AMM pool yet, still on bonding curve
                quote_mint=WSOL_MINT,
                source="pumpfun",
                signature=sig,
                slot=slot,
            )
            await self._queue.put(event)
            logger.info(f"New Pump.fun token | mint={mint[:8]}…")

        except Exception as e:
            logger.error(f"Error handling Pump.fun log {sig[:16]}…: {e}")

    def _extract_accounts(self, tx: dict) -> list[str]:
        """Extract account keys from a parsed transaction."""
        try:
            # Handle both legacy and versioned transaction formats
            msg = tx.get("transaction", {}).get("message", {})
            account_keys = msg.get("accountKeys", [])

            if not account_keys:
                return []

            # accountKeys can be list of strings or list of dicts
            if isinstance(account_keys[0], str):
                return account_keys
            elif isinstance(account_keys[0], dict):
                return [ak.get("pubkey", "") for ak in account_keys]
        except Exception:
            pass
        return []

    def _find_pumpfun_mint(self, accounts: list[str]) -> Optional[str]:
        """
        Heuristic: pump.fun mint is the 3rd account in the instruction
        (after the program and the bonding curve PDA).
        Falls back to scanning for a non-program account.
        """
        _known_programs = {
            PUMPFUN_PROGRAM,
            "11111111111111111111111111111111",
            "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
            "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJe1bm",
            "SysvarRent111111111111111111111111111111111",
            "SysvarC1ock11111111111111111111111111111111",
        }
        for acc in accounts:
            if acc not in _known_programs and len(acc) >= 32:
                return acc
        return None
