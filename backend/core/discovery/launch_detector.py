"""
LaunchDetector orchestrates the discovery pipeline.

It:
  1. Receives raw PoolEvents from PoolListener
  2. Runs each candidate through the filter pipeline
  3. Moves passing candidates into WATCHING state
  4. Monitors watch window via SwapListener
  5. Emits READY candidates to the strategy layer via out_queue
"""
from __future__ import annotations

import asyncio
import time
from typing import Optional

from loguru import logger

from core.discovery.pool_listener import PoolEvent, PoolListener
from core.discovery.swap_listener import SwapListener
from core.filters.token_score import FilterPipeline
from core.models.token import TokenCandidate, TokenState
from core.utils.ids import event_id


class LaunchDetector:
    def __init__(
        self,
        rpc_http: str,
        rpc_ws: str,
        filter_pipeline: FilterPipeline,
        ready_queue: asyncio.Queue,        # candidates that passed and are READY
        event_queue: asyncio.Queue,        # all TradeEvents for logging
        settings: dict,
    ) -> None:
        self._rpc_http = rpc_http
        self._rpc_ws = rpc_ws
        self._filters = filter_pipeline
        self._ready_q = ready_queue
        self._event_q = event_queue
        self._settings = settings

        self._pool_q: asyncio.Queue[PoolEvent] = asyncio.Queue()
        self._candidates: dict[str, TokenCandidate] = {}   # mint → candidate

        disc = settings.get("discovery", {})
        self._watch_window = disc.get("watch_window_seconds", 120)
        self._max_pipeline = disc.get("max_pipeline_size", 50)

        self._pool_listener = PoolListener(
            rpc_http=rpc_http,
            rpc_ws=rpc_ws,
            out_queue=self._pool_q,
        )
        self._swap_listener = SwapListener(poll_interval_seconds=2.0)

    # ── Entry point ───────────────────────────────────────────────────────────

    async def run(self) -> None:
        logger.info("LaunchDetector starting…")
        await asyncio.gather(
            self._pool_listener.run(),
            self._swap_listener.run(),
            self._process_pool_events(),
            self._monitor_watch_states(),
        )

    # ── Pool event processing ─────────────────────────────────────────────────

    async def _process_pool_events(self) -> None:
        while True:
            try:
                event: PoolEvent = await asyncio.wait_for(self._pool_q.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

            mint = event.mint
            if mint in self._candidates:
                continue   # Already seen this token

            if len(self._candidates) >= self._max_pipeline:
                logger.warning("Pipeline full — dropping candidate")
                continue

            candidate = TokenCandidate(
                mint=mint,
                pool_address=event.pool_address or None,
                source=event.source,
            )
            self._candidates[mint] = candidate

            logger.info(f"New candidate detected | {mint[:8]}… source={event.source}")

            # Run filters in a separate task so we don't block the event loop
            asyncio.create_task(self._run_filters(candidate))

    async def _run_filters(self, candidate: TokenCandidate) -> None:
        """Run filter pipeline. Moves to WATCHING or REJECTED."""
        candidate.transition(TokenState.FILTERING)
        candidate.filter_start_ts = time.time()

        passed = await self._filters.run(candidate)

        if not passed:
            logger.info(
                f"REJECTED | {candidate.mint[:8]}… reason={candidate.reject_reason}"
            )
            await self._emit_filter_event(candidate, passed=False)
            return

        await self._emit_filter_event(candidate, passed=True)

        # Start watching
        candidate.transition(TokenState.WATCHING)
        candidate.watch_start_ts = time.time()
        logger.info(f"WATCHING | {candidate.mint[:8]}… liq=${candidate.liquidity_usd:.0f}")

        # Subscribe to price feed
        self._swap_listener.watch(
            candidate.mint,
            on_price_update=lambda mint, price: self._on_price_update(mint, price),
        )

    def _on_price_update(self, mint: str, price: float) -> None:
        candidate = self._candidates.get(mint)
        if candidate is None or candidate.state != TokenState.WATCHING:
            return
        candidate.record_price(price)

    # ── Watch window monitor ──────────────────────────────────────────────────

    async def _monitor_watch_states(self) -> None:
        """
        Periodically check candidates in WATCHING state.
        Expire ones that have been watching too long without triggering.
        """
        while True:
            await asyncio.sleep(5)
            now = time.time()
            expired = []

            for mint, candidate in list(self._candidates.items()):
                if candidate.state != TokenState.WATCHING:
                    continue

                elapsed = now - (candidate.watch_start_ts or now)
                if elapsed > self._watch_window:
                    candidate.reject("watch_window_expired")
                    self._swap_listener.unwatch(mint)
                    logger.info(f"Watch window expired | {mint[:8]}…")
                    expired.append(mint)

            # Clean up terminal states periodically
            for mint, candidate in list(self._candidates.items()):
                if candidate.state in (TokenState.REJECTED, TokenState.CLOSED):
                    age = now - candidate.first_seen_ts
                    if age > 600:   # Keep for 10 min then purge
                        del self._candidates[mint]

    # ── External API: mark a candidate as READY ───────────────────────────────

    async def mark_ready(self, mint: str) -> None:
        """Called by strategy layer when it decides to enter."""
        candidate = self._candidates.get(mint)
        if candidate is None or candidate.state != TokenState.WATCHING:
            return
        candidate.transition(TokenState.READY)
        self._swap_listener.unwatch(mint)
        await self._ready_q.put(candidate)
        logger.info(f"READY | {candidate.mint[:8]}…")

    def get_watching(self) -> list[TokenCandidate]:
        return [
            c for c in self._candidates.values()
            if c.state == TokenState.WATCHING
        ]

    def get_candidate(self, mint: str) -> Optional[TokenCandidate]:
        return self._candidates.get(mint)

    # ── Event emission ────────────────────────────────────────────────────────

    async def _emit_filter_event(self, candidate: TokenCandidate, passed: bool) -> None:
        from core.models.trade_event import filter_event
        evt = filter_event(
            event_id=event_id(),
            mint=candidate.mint,
            passed=passed,
            reason=candidate.reject_reason or "ok",
            score=candidate.suspicious_score,
        )
        await self._event_q.put(evt)
