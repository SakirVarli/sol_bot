"""
PositionManager: owns all open positions.

In paper mode: simulates fills at current price, tracks virtual P&L.
In live mode: delegates to the execution layer.

Responsibilities:
  - Accept entry signals
  - Create and track positions
  - Apply exit rules (TP1, trailing stop, hard stop, time stop)
  - Emit POSITION_CLOSED events when done
"""
from __future__ import annotations

import asyncio
import time
from typing import Optional

from loguru import logger

from core.models.position import Position, PositionStatus, ExitReason, PartialFill
from core.models.signal import Signal, SignalType
from core.models.trade_event import TradeEvent, position_closed_event
from core.storage.trade_log import TradeLog
from core.utils.ids import position_id, event_id
from core.utils.math_utils import (
    take_profit_price,
    stop_loss_price,
    trailing_stop_price,
    sol_to_lamports,
)


class PositionManager:
    def __init__(
        self,
        trade_log: TradeLog,
        event_queue: asyncio.Queue,
        settings: dict,
        mode: str = "paper",
    ) -> None:
        self._log = trade_log
        self._event_q = event_queue
        self._mode = mode
        self._positions: dict[str, Position] = {}   # mint → Position

        pos_cfg = settings.get("position", {})
        self._tp1_pct = pos_cfg.get("tp1_pct", 40.0)
        self._tp1_fraction = pos_cfg.get("tp1_sell_fraction", 0.5)
        self._trail_pct = pos_cfg.get("trailing_stop_pct", 25.0)
        self._hard_stop_pct = pos_cfg.get("hard_stop_pct", -15.0)
        self._max_hold_minutes = pos_cfg.get("max_hold_minutes", 10)

        risk_cfg = settings.get("risk", {})
        self._max_concurrent = risk_cfg.get("max_concurrent_positions", 1)

    # ── External API ──────────────────────────────────────────────────────────

    def can_enter(self) -> bool:
        open_count = sum(
            1 for p in self._positions.values()
            if p.status in (PositionStatus.PENDING, PositionStatus.OPEN, PositionStatus.PARTIAL_EXIT)
        )
        return open_count < self._max_concurrent

    async def on_signal(self, signal: Signal, current_price: float) -> Optional[Position]:
        """Handle an ENTER signal. Creates a position (paper or live)."""
        if signal.signal_type != SignalType.ENTER:
            return None

        mint = signal.mint
        if mint in self._positions and self._positions[mint].status in (
            PositionStatus.OPEN, PositionStatus.PENDING, PositionStatus.PARTIAL_EXIT
        ):
            logger.warning(f"Already have an open position for {mint[:8]}…")
            return None

        if not self.can_enter():
            logger.warning("Max concurrent positions reached — skipping entry")
            return None

        pos = await self._open_position(signal, current_price)
        return pos

    async def on_price_update(self, mint: str, price: float) -> None:
        """Called whenever price changes for a token we hold."""
        pos = self._positions.get(mint)
        if pos is None or pos.status not in (
            PositionStatus.OPEN, PositionStatus.PARTIAL_EXIT
        ):
            return

        pos.update_price(price)
        await self._check_exits(pos)

    # ── Position lifecycle ────────────────────────────────────────────────────

    async def _open_position(self, signal: Signal, price: float) -> Position:
        size_sol = signal.suggested_size_sol
        # Simulate slippage in paper mode
        fill_price = price * (1 + signal.suggested_slippage_bps / 10_000)
        quantity = size_sol / fill_price if fill_price > 0 else 0

        pos = Position(
            position_id=position_id(),
            mint=signal.mint,
            mode=self._mode,
            entry_ts=time.time(),
            entry_price=fill_price,
            quantity=quantity,
            cost_sol=size_sol,
            current_price=fill_price,
            highest_price=fill_price,
            status=PositionStatus.OPEN,
            tp1_price=take_profit_price(fill_price, self._tp1_pct),
            tp1_fraction=self._tp1_fraction,
            trailing_stop_pct=self._trail_pct,
            hard_stop_price=stop_loss_price(fill_price, self._hard_stop_pct),
            time_stop_ts=time.time() + self._max_hold_minutes * 60,
        )

        self._positions[signal.mint] = pos
        await self._log.upsert_position(pos)

        logger.info(
            f"{'[PAPER]' if self._mode == 'paper' else '[LIVE]'} "
            f"ENTERED | {signal.mint[:8]}… "
            f"price={fill_price:.8f} size={size_sol:.3f} SOL "
            f"tp1={pos.tp1_price:.8f} stop={pos.hard_stop_price:.8f}"
        )

        await self._event_q.put(TradeEvent(
            event_id=event_id(),
            mint=signal.mint,
            event_type="BUY_FILLED",
            position_id=pos.position_id,
            price=fill_price,
            liquidity_usd=signal.liquidity_usd,
            details={
                "size_sol": size_sol,
                "quantity": quantity,
                "strategy": signal.strategy,
                "mode": self._mode,
            },
        ))
        return pos

    async def _check_exits(self, pos: Position) -> None:
        price = pos.current_price

        # TP1: first take profit
        if not pos.tp1_triggered and price >= pos.tp1_price:
            await self._partial_exit(pos, pos.tp1_fraction, ExitReason.TP1)
            pos.tp1_triggered = True

        # Trailing stop (only after TP1)
        if pos.tp1_triggered:
            trail_price = trailing_stop_price(pos.highest_price, pos.trailing_stop_pct)
            if price <= trail_price:
                await self._full_exit(pos, ExitReason.TRAILING_STOP)
                return

        # Hard stop (always active)
        if price <= pos.hard_stop_price:
            await self._full_exit(pos, ExitReason.HARD_STOP)
            return

        # Time stop
        if pos.is_past_time_stop():
            await self._full_exit(pos, ExitReason.TIME_STOP)
            return

    async def _partial_exit(self, pos: Position, fraction: float, reason: ExitReason) -> None:
        sell_qty = pos.quantity * fraction
        sell_price = pos.current_price
        proceeds_sol = sell_qty * sell_price
        cost_fraction = pos.cost_sol * fraction

        pos.realized_pnl_sol += proceeds_sol - cost_fraction
        pos.quantity -= sell_qty
        pos.cost_sol -= cost_fraction
        pos.status = PositionStatus.PARTIAL_EXIT

        pos.exit_fills.append(PartialFill(
            ts=time.time(),
            quantity=sell_qty,
            price=sell_price,
            reason=reason.value,
        ))

        await self._log.upsert_position(pos)

        logger.info(
            f"{'[PAPER]' if self._mode == 'paper' else '[LIVE]'} "
            f"PARTIAL EXIT ({reason.value}) | {pos.mint[:8]}… "
            f"sold {fraction*100:.0f}% at {sell_price:.8f} | "
            f"realized={pos.realized_pnl_sol:+.4f} SOL"
        )

        await self._event_q.put(TradeEvent(
            event_id=event_id(),
            mint=pos.mint,
            event_type="SELL_FILLED",
            position_id=pos.position_id,
            price=sell_price,
            pnl_sol=pos.realized_pnl_sol,
            pnl_pct=pos.pnl_pct(),
            details={"reason": reason.value, "fraction": fraction, "qty": sell_qty},
        ))

    async def _full_exit(self, pos: Position, reason: ExitReason) -> None:
        sell_price = pos.current_price
        proceeds_sol = pos.quantity * sell_price
        pos.realized_pnl_sol += proceeds_sol - pos.cost_sol
        pos.quantity = 0
        pos.cost_sol = 0
        pos.status = PositionStatus.CLOSED
        pos.exit_reason = reason
        pos.close_ts = time.time()

        await self._log.upsert_position(pos)

        logger.info(
            f"{'[PAPER]' if self._mode == 'paper' else '[LIVE]'} "
            f"CLOSED ({reason.value}) | {pos.mint[:8]}… "
            f"pnl={pos.realized_pnl_sol:+.4f} SOL ({pos.pnl_pct():+.1f}%) "
            f"hold={pos.hold_seconds():.0f}s"
        )

        await self._event_q.put(position_closed_event(
            event_id=event_id(),
            mint=pos.mint,
            position_id=pos.position_id,
            exit_reason=reason.value,
            pnl_sol=pos.realized_pnl_sol,
            pnl_pct=pos.pnl_pct(),
            hold_seconds=pos.hold_seconds(),
        ))

        # Remove from active positions
        del self._positions[pos.mint]

    # ── Introspection ─────────────────────────────────────────────────────────

    def get_open_positions(self) -> list[Position]:
        return list(self._positions.values())

    def get_position(self, mint: str) -> Optional[Position]:
        return self._positions.get(mint)
