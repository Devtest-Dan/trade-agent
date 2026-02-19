"""Strategy Engine — evaluates parsed strategies against live market data."""

import asyncio
from datetime import datetime
from typing import Any, Callable

from loguru import logger

from agent.data_manager import DataManager
from agent.models.market import IndicatorValue
from agent.models.signal import Signal, SignalDirection, SignalStatus
from agent.models.strategy import (
    Autonomy,
    Condition,
    ConditionGroup,
    Rule,
    Strategy,
    StrategyConfig,
)


class StrategyEngine:
    def __init__(self, data_manager: DataManager):
        self.data_manager = data_manager
        self._strategies: dict[int, Strategy] = {}
        self._signal_callbacks: list[Callable] = []

        # Track previous indicator values for cross detection
        # Key: (strategy_id, indicator_id), Value: dict of field → value
        self._prev_values: dict[tuple[int, str], dict[str, float]] = {}

    def on_signal(self, callback: Callable):
        """Register callback for signal events: callback(Signal)."""
        self._signal_callbacks.append(callback)

    def load_strategy(self, strategy: Strategy):
        """Load/reload a strategy into the engine."""
        if strategy.id is None:
            return
        self._strategies[strategy.id] = strategy
        logger.info(f"Loaded strategy: {strategy.name} (id={strategy.id})")

        # Subscribe data manager to needed timeframes
        for symbol in strategy.config.symbols:
            self.data_manager.subscribe(symbol, strategy.config.timeframes_used)

    def unload_strategy(self, strategy_id: int):
        """Remove a strategy from the engine."""
        if strategy_id in self._strategies:
            del self._strategies[strategy_id]
            logger.info(f"Unloaded strategy id={strategy_id}")

    async def evaluate_on_bar_close(self, symbol: str, timeframe: str):
        """Called when a bar closes — evaluate all strategies that use this symbol/timeframe."""
        for sid, strategy in self._strategies.items():
            if not strategy.enabled:
                continue
            if symbol not in strategy.config.symbols:
                continue
            if timeframe not in strategy.config.timeframes_used:
                continue

            # Refresh indicator values for this timeframe
            await self.data_manager.refresh_indicators(
                symbol, timeframe, [i.model_dump() for i in strategy.config.indicators]
            )

            # Evaluate all condition groups
            await self._evaluate_strategy(strategy, symbol)

    async def _evaluate_strategy(self, strategy: Strategy, symbol: str):
        """Evaluate entry/exit conditions for a strategy on a symbol."""
        config = strategy.config
        sid = strategy.id

        # Build current values dict for all indicators
        current_values = self._get_current_values(strategy, symbol)

        # Check entry_long
        if self._evaluate_group(
            config.conditions.get("entry_long", ConditionGroup()),
            current_values,
            sid,
        ):
            await self._emit_signal(strategy, symbol, SignalDirection.LONG)

        # Check entry_short
        if self._evaluate_group(
            config.conditions.get("entry_short", ConditionGroup()),
            current_values,
            sid,
        ):
            await self._emit_signal(strategy, symbol, SignalDirection.SHORT)

        # Check exit_long
        if self._evaluate_group(
            config.conditions.get("exit_long", ConditionGroup(type="OR")),
            current_values,
            sid,
        ):
            await self._emit_signal(strategy, symbol, SignalDirection.EXIT_LONG)

        # Check exit_short
        if self._evaluate_group(
            config.conditions.get("exit_short", ConditionGroup(type="OR")),
            current_values,
            sid,
        ):
            await self._emit_signal(strategy, symbol, SignalDirection.EXIT_SHORT)

        # Update previous values for next cross detection
        for ind_id, vals in current_values.items():
            self._prev_values[(sid, ind_id)] = vals.copy()

    def _get_current_values(
        self, strategy: Strategy, symbol: str
    ) -> dict[str, dict[str, float]]:
        """Get current indicator values for all indicators in a strategy."""
        result = {}
        for ind in strategy.config.indicators:
            iv = self.data_manager.get_cached_indicator(symbol, ind.timeframe, ind.id)
            if iv:
                result[ind.id] = iv.values.copy()

                # Add price comparison
                tick = self.data_manager.get_tick(symbol)
                if tick:
                    result[ind.id]["_price"] = (tick.bid + tick.ask) / 2
        return result

    def _evaluate_group(
        self,
        group: ConditionGroup,
        current_values: dict[str, dict[str, float]],
        strategy_id: int,
    ) -> bool:
        """Evaluate a condition group (AND/OR of rules)."""
        if not group.rules:
            return False

        results = []
        for rule in group.rules:
            result = self._evaluate_rule(rule, current_values, strategy_id)
            results.append(result)

        if group.type == "AND":
            return all(results)
        else:  # OR
            return any(results)

    def _evaluate_rule(
        self,
        rule: Rule,
        current_values: dict[str, dict[str, float]],
        strategy_id: int,
    ) -> bool:
        """Evaluate a single rule/condition."""
        cond = rule.condition
        ind_id = cond.indicator
        field = cond.field

        vals = current_values.get(ind_id)
        if vals is None:
            return False

        # Handle cross_above / cross_below (comparing with a threshold)
        if field.startswith("cross_"):
            return self._evaluate_cross(cond, vals, strategy_id, ind_id)

        # Get the indicator value for the specified field
        current = vals.get(field)
        if current is None:
            # Try "value" as fallback for single-output indicators
            current = vals.get("value")
            if current is None:
                return False

        # Get comparison value
        if cond.compare_to == "price":
            compare_val = vals.get("_price")
            if compare_val is None:
                return False
        elif cond.compare_to:
            # Compare to another indicator
            other_vals = current_values.get(cond.compare_to)
            if other_vals is None:
                return False
            compare_val = other_vals.get("value", other_vals.get(field))
            if compare_val is None:
                return False
        elif cond.value is not None:
            compare_val = cond.value
        else:
            return False

        # Apply operator
        op = cond.operator
        if op == "<":
            return current < compare_val
        elif op == ">":
            return current > compare_val
        elif op == "<=":
            return current <= compare_val
        elif op == ">=":
            return current >= compare_val
        elif op == "==":
            return abs(current - compare_val) < 1e-8
        else:
            return False

    def _evaluate_cross(
        self,
        cond: Condition,
        current_values: dict[str, float],
        strategy_id: int,
        indicator_id: str,
    ) -> bool:
        """Evaluate cross_above or cross_below conditions."""
        field = cond.field
        threshold = cond.value
        if threshold is None:
            return False

        # Get current value — for stochastic use "k", otherwise "value"
        current = current_values.get("k", current_values.get("value"))
        if current is None:
            return False

        # Get previous value
        prev_key = (strategy_id, indicator_id)
        prev_vals = self._prev_values.get(prev_key)
        if prev_vals is None:
            return False
        prev = prev_vals.get("k", prev_vals.get("value"))
        if prev is None:
            return False

        if field == "cross_above":
            return prev <= threshold and current > threshold
        elif field == "cross_below":
            return prev >= threshold and current < threshold

        return False

    async def _emit_signal(
        self, strategy: Strategy, symbol: str, direction: SignalDirection
    ):
        """Emit a trading signal."""
        tick = self.data_manager.get_tick(symbol)
        price = ((tick.bid + tick.ask) / 2) if tick else 0.0

        # Build conditions snapshot
        snapshot = {}
        for ind in strategy.config.indicators:
            iv = self.data_manager.get_cached_indicator(symbol, ind.timeframe, ind.id)
            if iv:
                snapshot[ind.id] = {
                    "name": ind.name,
                    "timeframe": ind.timeframe,
                    "values": iv.values,
                }

        signal = Signal(
            strategy_id=strategy.id or 0,
            strategy_name=strategy.name,
            symbol=symbol,
            direction=direction,
            conditions_snapshot=snapshot,
            price_at_signal=price,
            status=SignalStatus.PENDING,
            created_at=datetime.now(),
        )

        logger.info(
            f"SIGNAL: {direction.value} {symbol} | Strategy: {strategy.name} | Price: {price}"
        )

        for cb in self._signal_callbacks:
            try:
                result = cb(signal)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(f"Signal callback error: {e}")
