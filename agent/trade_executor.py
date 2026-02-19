"""Trade Executor — routes approved signals to MT5 or notifications."""

import asyncio
from datetime import datetime
from typing import Any, Callable

from loguru import logger

from agent.bridge import ZMQBridge
from agent.models.signal import Signal, SignalDirection, SignalStatus
from agent.models.strategy import Autonomy, Strategy
from agent.models.trade import Trade
from agent.risk_manager import RiskDecision, RiskManager


class TradeExecutor:
    def __init__(self, bridge: ZMQBridge, risk_manager: RiskManager):
        self.bridge = bridge
        self.risk_manager = risk_manager
        self._trade_callbacks: list[Callable] = []
        self._notification_callbacks: list[Callable] = []

    def on_trade(self, callback: Callable):
        """Register callback for trade events."""
        self._trade_callbacks.append(callback)

    def on_notification(self, callback: Callable):
        """Register callback for signal notifications (signal-only mode)."""
        self._notification_callbacks.append(callback)

    async def process_signal(
        self, signal: Signal, strategy: Strategy, risk_decision: RiskDecision
    ) -> Signal:
        """Process a signal based on risk decision and autonomy level."""
        autonomy = strategy.config.autonomy

        if not risk_decision.approved:
            signal.status = SignalStatus.REJECTED
            signal.ai_reasoning = f"Blocked by risk manager: {risk_decision.reason}"
            logger.warning(
                f"Signal BLOCKED: {signal.direction.value} {signal.symbol} — {risk_decision.reason}"
            )

            # Kill action: disable the strategy
            if risk_decision.action == "kill":
                strategy.enabled = False
                logger.critical(
                    f"Strategy '{strategy.name}' AUTO-PAUSED due to: {risk_decision.reason}"
                )

            return signal

        # Route based on autonomy
        if autonomy == Autonomy.SIGNAL_ONLY:
            signal.status = SignalStatus.PENDING
            await self._notify(signal)
            return signal

        elif autonomy in (Autonomy.SEMI_AUTO, Autonomy.FULL_AUTO):
            return await self._execute_trade(signal, strategy)

        return signal

    async def _execute_trade(self, signal: Signal, strategy: Strategy) -> Signal:
        """Execute a trade on MT5."""
        risk = strategy.config.risk

        # Determine order type
        if signal.direction == SignalDirection.LONG:
            order_type = "BUY"
        elif signal.direction == SignalDirection.SHORT:
            order_type = "SELL"
        elif signal.direction in (SignalDirection.EXIT_LONG, SignalDirection.EXIT_SHORT):
            # Close positions for this strategy/symbol
            return await self._close_positions(signal, strategy)
        else:
            signal.status = SignalStatus.REJECTED
            return signal

        # Execute market order
        result = await self.bridge.open_order(
            symbol=signal.symbol,
            order_type=order_type,
            lot=risk.max_lot,
        )

        if result.get("success"):
            signal.status = SignalStatus.EXECUTED
            ticket = result.get("ticket", 0)

            trade = Trade(
                signal_id=signal.id,
                strategy_id=signal.strategy_id,
                symbol=signal.symbol,
                direction=order_type,
                lot=risk.max_lot,
                open_price=signal.price_at_signal,
                ticket=ticket,
                open_time=datetime.now(),
            )

            self.risk_manager.record_trade(signal.strategy_id)

            logger.info(
                f"TRADE EXECUTED: {order_type} {signal.symbol} {risk.max_lot} lot | Ticket: {ticket}"
            )

            for cb in self._trade_callbacks:
                try:
                    result = cb(trade)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as e:
                    logger.error(f"Trade callback error: {e}")
        else:
            signal.status = SignalStatus.REJECTED
            signal.ai_reasoning = f"Order failed: {result.get('error', 'Unknown error')}"
            logger.error(f"TRADE FAILED: {result.get('error')}")

        return signal

    async def _close_positions(self, signal: Signal, strategy: Strategy) -> Signal:
        """Close open positions matching the exit signal."""
        positions = await self.bridge.get_positions()

        target_dir = (
            "BUY" if signal.direction == SignalDirection.EXIT_LONG else "SELL"
        )

        closed = 0
        for pos in positions:
            if pos.symbol == signal.symbol and pos.direction == target_dir:
                result = await self.bridge.close_order(pos.ticket)
                if result.get("success"):
                    closed += 1
                    logger.info(f"Closed position: ticket {pos.ticket}")

        if closed > 0:
            signal.status = SignalStatus.EXECUTED
            signal.ai_reasoning = f"Closed {closed} {target_dir} position(s)"
        else:
            signal.status = SignalStatus.EXPIRED
            signal.ai_reasoning = "No matching positions to close"

        return signal

    async def _notify(self, signal: Signal):
        """Send notification for signal-only mode."""
        for cb in self._notification_callbacks:
            try:
                result = cb(signal)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(f"Notification callback error: {e}")

    async def execute_kill_switch(self) -> int:
        """Emergency: close all open positions."""
        positions = await self.bridge.get_positions()
        closed = 0
        for pos in positions:
            result = await self.bridge.close_order(pos.ticket)
            if result.get("success"):
                closed += 1
        logger.critical(f"KILL SWITCH: Closed {closed}/{len(positions)} positions")
        return closed
