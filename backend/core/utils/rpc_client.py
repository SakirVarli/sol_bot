"""
Lightweight async Solana JSON-RPC client.
Uses httpx for HTTP calls and websockets for subscriptions.
"""
from __future__ import annotations

import asyncio
import base64
import json
import struct
from typing import Any, AsyncIterator, Callable, Optional

import httpx
from loguru import logger


# ── Known program IDs ─────────────────────────────────────────────────────────

WSOL_MINT = "So11111111111111111111111111111111111111112"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
SPL_TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"


# ── RPC HTTP client ───────────────────────────────────────────────────────────

class SolanaRPC:
    """Async Solana JSON-RPC HTTP client."""

    def __init__(self, endpoint: str, timeout: float = 10.0) -> None:
        self.endpoint = endpoint
        self._client = httpx.AsyncClient(timeout=timeout)
        self._id = 0

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    async def call(self, method: str, params: list[Any] | None = None) -> Any:
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": method,
            "params": params or [],
        }
        try:
            resp = await self._client.post(self.endpoint, json=payload)
            resp.raise_for_status()
            data = resp.json()
            if "error" in data:
                raise RuntimeError(f"RPC error: {data['error']}")
            return data.get("result")
        except Exception as e:
            logger.error(f"RPC call failed [{method}]: {e}")
            raise

    async def get_account_info(self, pubkey: str, encoding: str = "base64") -> Optional[dict]:
        result = await self.call(
            "getAccountInfo",
            [pubkey, {"encoding": encoding, "commitment": "confirmed"}],
        )
        if result is None or result.get("value") is None:
            return None
        return result["value"]

    async def get_token_supply(self, mint: str) -> Optional[dict]:
        result = await self.call("getTokenSupply", [mint, {"commitment": "confirmed"}])
        if result is None:
            return None
        return result.get("value")

    async def get_token_largest_accounts(self, mint: str) -> list[dict]:
        result = await self.call(
            "getTokenLargestAccounts", [mint, {"commitment": "confirmed"}]
        )
        if result is None:
            return []
        return result.get("value", [])

    async def get_transaction(self, signature: str) -> Optional[dict]:
        result = await self.call(
            "getTransaction",
            [
                signature,
                {
                    "encoding": "json",
                    "maxSupportedTransactionVersion": 0,
                    "commitment": "confirmed",
                },
            ],
        )
        return result

    async def get_balance(self, pubkey: str) -> int:
        """Returns balance in lamports."""
        result = await self.call("getBalance", [pubkey, {"commitment": "confirmed"}])
        if result is None:
            return 0
        return result.get("value", 0)

    async def close(self) -> None:
        await self._client.aclose()


# ── Mint account parsing ──────────────────────────────────────────────────────
# SPL Token Mint layout (82 bytes):
# [0:4]   mint_authority_option  (u32: 0=None, 1=Some)
# [4:36]  mint_authority         (Pubkey, 32 bytes)
# [36:44] supply                 (u64)
# [44]    decimals               (u8)
# [45]    is_initialized         (bool)
# [46:50] freeze_authority_option (u32)
# [50:82] freeze_authority       (Pubkey, 32 bytes)

def parse_mint_account(data_b64: str) -> dict:
    """Parse a base64-encoded SPL token mint account."""
    import base64 as _b64
    data = _b64.b64decode(data_b64)
    if len(data) < 82:
        return {}

    mint_auth_option = struct.unpack_from("<I", data, 0)[0]
    supply = struct.unpack_from("<Q", data, 36)[0]
    decimals = data[44]
    is_initialized = bool(data[45])
    freeze_auth_option = struct.unpack_from("<I", data, 46)[0]

    return {
        "has_mint_authority": mint_auth_option == 1,
        "supply": supply,
        "decimals": decimals,
        "is_initialized": is_initialized,
        "has_freeze_authority": freeze_auth_option == 1,
    }


# ── WebSocket subscription helper ─────────────────────────────────────────────

class SolanaWS:
    """
    Thin wrapper around a Solana WebSocket connection.
    Handles reconnection and subscription management.
    """

    def __init__(self, endpoint: str, ping_interval: float = 20.0) -> None:
        self.endpoint = endpoint
        self.ping_interval = ping_interval
        self._sub_id = 0
        self._handlers: dict[int, Callable] = {}   # ws_sub_id → callback
        self._running = False

    def _next_id(self) -> int:
        self._sub_id += 1
        return self._sub_id

    async def subscribe_logs(
        self,
        program_id: str,
        callback: Callable[[dict], None],
        commitment: str = "confirmed",
    ) -> int:
        """Register a logs subscription. Returns local sub ID (used for tracking)."""
        sub_id = self._next_id()
        self._handlers[sub_id] = (program_id, callback)
        return sub_id

    async def run(self) -> None:
        """
        Main loop: connect, subscribe to all registered programs, dispatch callbacks.
        Reconnects on failure.
        """
        import websockets

        self._running = True
        while self._running:
            try:
                await self._connect_and_listen()
            except Exception as e:
                logger.warning(f"WebSocket disconnected: {e}. Reconnecting in 3s…")
                await asyncio.sleep(3)

    async def _connect_and_listen(self) -> None:
        import websockets

        async with websockets.connect(
            self.endpoint,
            ping_interval=self.ping_interval,
            max_size=10 * 1024 * 1024,  # 10 MB
        ) as ws:
            logger.info(f"WebSocket connected to {self.endpoint}")

            # Map: ws subscription id → callback
            ws_sub_map: dict[int, Callable] = {}

            # Send all subscriptions
            req_id = 1
            pending_reqs: dict[int, Callable] = {}
            for local_id, (program_id, callback) in self._handlers.items():
                sub_req = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "method": "logsSubscribe",
                    "params": [
                        {"mentions": [program_id]},
                        {"commitment": "confirmed"},
                    ],
                }
                await ws.send(json.dumps(sub_req))
                pending_reqs[req_id] = callback
                req_id += 1

            async for raw in ws:
                msg = json.loads(raw)

                # Subscription confirmation
                if "id" in msg and "result" in msg:
                    ws_sub_id = msg["result"]
                    callback = pending_reqs.pop(msg["id"], None)
                    if callback is not None:
                        ws_sub_map[ws_sub_id] = callback
                    continue

                # Notification
                if msg.get("method") == "logsNotification":
                    sub_id = msg["params"]["subscription"]
                    callback = ws_sub_map.get(sub_id)
                    if callback:
                        try:
                            await asyncio.coroutine(callback)(msg["params"]["result"])
                        except TypeError:
                            # callback is not a coroutine, wrap it
                            loop = asyncio.get_event_loop()
                            loop.call_soon(callback, msg["params"]["result"])

    def stop(self) -> None:
        self._running = False
