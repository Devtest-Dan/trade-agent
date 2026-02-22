"""Playbook Engine — deterministic state machine runner for execution playbooks.

Runs playbooks as local state machines with zero AI calls at runtime.
Parallel to StrategyEngine — both run on bar close events.
"""

import asyncio
from datetime import datetime
from typing import Any, Callable

from loguru import logger

from agent.data_manager import DataManager
from agent.models.playbook import (
    Playbook,
    PlaybookConfig,
    PlaybookState,
    Phase,
    Transition,
    PositionManagementRule,
)
from agent.models.signal import Signal, SignalDirection, SignalStatus
from agent.playbook_eval import ExpressionContext, evaluate_condition, evaluate_condition_detailed, evaluate_expr


class PlaybookInstance:
    """Runtime instance of a single playbook for a single symbol."""

    def __init__(self, playbook: Playbook, symbol: str, state: PlaybookState | None = None):
        self.playbook = playbook
        self.config = playbook.config
        self.symbol = symbol
        self.state = state or PlaybookState(
            playbook_id=playbook.id,
            symbol=symbol,
            current_phase=playbook.config.initial_phase,
            variables={
                name: var.default
                for name, var in playbook.config.variables.items()
            },
        )
        # Per-rule tracking (populated on transition fires)
        self.last_fired_rules: list[dict] = []
        self.last_fired_transition: str = ""

    @property
    def current_phase(self) -> Phase | None:
        return self.config.phases.get(self.state.current_phase)

    def transition_to(self, phase_name: str):
        """Transition to a new phase, resetting phase-specific counters."""
        logger.info(
            f"Playbook '{self.config.name}' [{self.symbol}]: "
            f"{self.state.current_phase} -> {phase_name}"
        )
        self.state.current_phase = phase_name
        self.state.bars_in_phase = 0
        self.state.phase_timeframe_bars = {}
        self.state.fired_once_rules = []

    def set_variable(self, name: str, value: Any):
        self.state.variables[name] = value

    def build_context(
        self,
        indicators: dict[str, dict[str, float]],
        prev_indicators: dict[str, dict[str, float]],
        price: float,
        trade_data: dict[str, float] | None = None,
    ) -> ExpressionContext:
        """Build an expression context from current market state."""
        risk_dict = {
            "max_lot": self.config.risk.max_lot,
            "max_daily_trades": self.config.risk.max_daily_trades,
            "max_drawdown_pct": self.config.risk.max_drawdown_pct,
            "max_open_positions": self.config.risk.max_open_positions,
        }
        return ExpressionContext(
            indicators=indicators,
            prev_indicators=prev_indicators,
            variables=self.state.variables,
            price=price,
            trade=trade_data or {},
            risk=risk_dict,
        )


class PlaybookEngine:
    """Manages all active playbook instances and evaluates them on bar close."""

    def __init__(self, data_manager: DataManager):
        self.data_manager = data_manager
        self._instances: dict[int, PlaybookInstance] = {}  # playbook_id -> instance
        self._signal_callbacks: list[Callable] = []
        self._trade_action_callbacks: list[Callable] = []
        self._management_callbacks: list[Callable] = []
        self._state_change_callbacks: list[Callable] = []
        # Previous indicator values for each (symbol, indicator_id)
        self._prev_indicators: dict[tuple[str, str], dict[str, float]] = {}

    def on_signal(self, callback: Callable):
        """Register callback for playbook-generated signals."""
        self._signal_callbacks.append(callback)

    def on_trade_action(self, callback: Callable):
        """Register callback for trade actions (open/close/modify)."""
        self._trade_action_callbacks.append(callback)

    def on_management_event(self, callback: Callable):
        """Register callback for position management events."""
        self._management_callbacks.append(callback)

    def on_state_change(self, callback: Callable):
        """Register callback for state persistence."""
        self._state_change_callbacks.append(callback)

    def load_playbook(self, playbook: Playbook, state: PlaybookState | None = None):
        """Load a playbook into the engine."""
        if playbook.id is None:
            return
        for symbol in playbook.config.symbols:
            instance = PlaybookInstance(playbook, symbol, state)
            self._instances[playbook.id] = instance
            logger.info(
                f"Loaded playbook '{playbook.config.name}' (id={playbook.id}) "
                f"for {symbol}, phase={instance.state.current_phase}"
            )

    def unload_playbook(self, playbook_id: int):
        """Remove a playbook from the engine."""
        if playbook_id in self._instances:
            inst = self._instances.pop(playbook_id)
            logger.info(f"Unloaded playbook '{inst.config.name}' (id={playbook_id})")

    def get_instance(self, playbook_id: int) -> PlaybookInstance | None:
        return self._instances.get(playbook_id)

    def get_all_instances(self) -> dict[int, PlaybookInstance]:
        return dict(self._instances)

    async def evaluate_on_bar_close(self, symbol: str, timeframe: str):
        """Evaluate all active playbooks for a symbol/timeframe bar close."""
        for pb_id, instance in list(self._instances.items()):
            if not instance.playbook.enabled:
                continue
            if instance.symbol != symbol:
                continue

            phase = instance.current_phase
            if not phase:
                continue

            # Only evaluate if this timeframe is in the phase's evaluate_on list
            if timeframe not in phase.evaluate_on:
                continue

            try:
                await self._evaluate_instance(instance, timeframe)
            except Exception as e:
                logger.error(
                    f"Playbook '{instance.config.name}' evaluation error: {e}",
                    exc_info=True,
                )

    async def _evaluate_instance(self, instance: PlaybookInstance, timeframe: str):
        """Evaluate a single playbook instance."""
        config = instance.config
        state = instance.state
        phase = instance.current_phase
        if not phase:
            return

        # Refresh indicators for this timeframe
        for ind in config.indicators:
            if ind.timeframe == timeframe:
                await self.data_manager.fetch_indicator(
                    indicator_id=ind.id,
                    name=ind.name,
                    symbol=instance.symbol,
                    timeframe=ind.timeframe,
                    params=ind.params,
                )

        # Build indicator values dict
        indicators = self._collect_indicators(instance.symbol, config)
        prev_indicators = self._collect_prev_indicators(instance.symbol, config)

        # Get current price
        tick = self.data_manager.get_tick(instance.symbol)
        price = (tick.bid + tick.ask) / 2 if tick else 0.0

        # Build trade data if position is open
        trade_data = None
        if state.open_ticket:
            trade_data = await self._get_trade_data(state)

        ctx = instance.build_context(indicators, prev_indicators, price, trade_data)

        # Increment bar counters
        state.bars_in_phase += 1
        state.phase_timeframe_bars[timeframe] = (
            state.phase_timeframe_bars.get(timeframe, 0) + 1
        )

        # Check timeout first
        if phase.timeout:
            tf_bars = state.phase_timeframe_bars.get(phase.timeout.timeframe, 0)
            if tf_bars >= phase.timeout.bars:
                logger.info(
                    f"Playbook '{config.name}': phase '{state.current_phase}' "
                    f"timed out after {tf_bars} bars on {phase.timeout.timeframe}"
                )
                instance.transition_to(phase.timeout.to)
                await self._persist_state(instance)
                return

        # Evaluate transitions (sorted by priority descending)
        sorted_transitions = sorted(
            phase.transitions, key=lambda t: t.priority, reverse=True
        )
        for transition in sorted_transitions:
            cond_dict = transition.conditions.model_dump()
            try:
                passed, rule_details = evaluate_condition_detailed(cond_dict, ctx)
                if passed:
                    # Store per-rule results for tracking
                    instance.last_fired_rules = rule_details
                    instance.last_fired_transition = transition.to
                    # Execute transition actions
                    await self._execute_actions(
                        instance, transition, ctx, indicators, timeframe
                    )
                    # Transition to target phase
                    instance.transition_to(transition.to)
                    await self._persist_state(instance)
                    return
            except Exception as e:
                logger.warning(
                    f"Playbook '{config.name}' transition condition error: {e}"
                )

        # Evaluate position management rules if in a phase with them
        if phase.position_management and state.open_ticket:
            await self._evaluate_management(instance, phase, ctx, timeframe)

        # Update previous indicators
        self._update_prev_indicators(instance.symbol, config, indicators)

        # Persist state
        await self._persist_state(instance)

    async def _execute_actions(
        self,
        instance: PlaybookInstance,
        transition: Transition,
        ctx: ExpressionContext,
        indicators: dict[str, dict[str, float]],
        timeframe: str,
    ):
        """Execute actions from a transition."""
        for action in transition.actions:
            if action.set_var and action.expr:
                try:
                    val = evaluate_expr(action.expr, ctx)
                    instance.set_variable(action.set_var, val)
                    logger.debug(
                        f"Set var {action.set_var} = {val}"
                    )
                except Exception as e:
                    logger.warning(f"set_var failed: {e}")

            elif action.open_trade:
                await self._handle_open_trade(instance, action.open_trade, ctx, indicators, timeframe)

            elif action.close_trade:
                await self._handle_close_trade(instance)

            elif action.log:
                logger.info(f"Playbook log [{instance.config.name}]: {action.log}")

    async def _handle_open_trade(self, instance, trade_action, ctx, indicators, timeframe):
        """Emit a trade action for the trade executor to handle."""
        direction = trade_action.direction

        # Evaluate dynamic values
        lot = instance.config.risk.max_lot
        sl = None
        tp = None

        if trade_action.lot:
            try:
                lot = evaluate_expr(trade_action.lot.expr, ctx)
            except Exception as e:
                logger.warning(f"Lot expression failed: {e}, using default")

        if trade_action.sl:
            try:
                sl = evaluate_expr(trade_action.sl.expr, ctx)
            except Exception as e:
                logger.warning(f"SL expression failed: {e}")

        if trade_action.tp:
            try:
                tp = evaluate_expr(trade_action.tp.expr, ctx)
            except Exception as e:
                logger.warning(f"TP expression failed: {e}")

        # Store SL in variables for position management reference
        if sl is not None:
            instance.set_variable("initial_sl", sl)
        if tp is not None:
            instance.set_variable("initial_tp", tp)

        tick = self.data_manager.get_tick(instance.symbol)
        price = (tick.bid + tick.ask) / 2 if tick else 0.0

        # Create signal
        signal_dir = (
            SignalDirection.LONG if direction == "BUY" else SignalDirection.SHORT
        )
        signal = Signal(
            strategy_id=0,
            playbook_db_id=instance.playbook.id,
            playbook_phase=instance.state.current_phase,
            strategy_name=instance.config.name,
            symbol=instance.symbol,
            direction=signal_dir,
            conditions_snapshot={
                "playbook": instance.config.id,
                "phase": instance.state.current_phase,
                "indicators": indicators,
            },
            price_at_signal=price,
        )

        # Emit trade action
        trade_data = {
            "signal": signal,
            "playbook_id": instance.playbook.id,
            "direction": direction,
            "lot": lot,
            "sl": sl,
            "tp": tp,
            "symbol": instance.symbol,
            "entry_snapshot": indicators,
            "variables_at_entry": dict(instance.state.variables),
            "phase_at_entry": instance.state.current_phase,
            "fired_rules": instance.last_fired_rules,
            "fired_transition": instance.last_fired_transition,
        }

        for cb in self._signal_callbacks:
            try:
                result = cb(signal)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(f"Signal callback error: {e}")

        for cb in self._trade_action_callbacks:
            try:
                result = cb(trade_data)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(f"Trade action callback error: {e}")

    async def _handle_close_trade(self, instance: PlaybookInstance):
        """Emit a close trade action."""
        if not instance.state.open_ticket:
            return

        direction = instance.state.open_direction
        signal_dir = (
            SignalDirection.EXIT_LONG
            if direction == "BUY"
            else SignalDirection.EXIT_SHORT
        )
        signal = Signal(
            strategy_id=0,
            playbook_db_id=instance.playbook.id,
            playbook_phase=instance.state.current_phase,
            strategy_name=instance.config.name,
            symbol=instance.symbol,
            direction=signal_dir,
            price_at_signal=0.0,
        )

        for cb in self._signal_callbacks:
            try:
                result = cb(signal)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(f"Signal callback error: {e}")

    async def _evaluate_management(
        self,
        instance: PlaybookInstance,
        phase: Phase,
        ctx: ExpressionContext,
        timeframe: str,
    ):
        """Evaluate position management rules."""
        for rule in phase.position_management:
            # Skip once-only rules that already fired
            if rule.once and rule.name in instance.state.fired_once_rules:
                continue

            # Evaluate condition
            cond_dict = rule.when.model_dump()
            try:
                if not evaluate_condition(cond_dict, ctx):
                    continue
            except Exception as e:
                logger.warning(f"Management rule '{rule.name}' condition error: {e}")
                continue

            logger.info(
                f"Playbook '{instance.config.name}': management rule '{rule.name}' fired"
            )

            # Execute the action
            event_details = {"rule": rule.name}

            if rule.modify_sl:
                try:
                    new_sl = evaluate_expr(rule.modify_sl.expr, ctx)
                    event_details["action"] = "modify_sl"
                    event_details["new_sl"] = new_sl
                    await self._emit_management_event(instance, event_details)
                except Exception as e:
                    logger.warning(f"modify_sl failed: {e}")

            elif rule.modify_tp:
                try:
                    new_tp = evaluate_expr(rule.modify_tp.expr, ctx)
                    event_details["action"] = "modify_tp"
                    event_details["new_tp"] = new_tp
                    await self._emit_management_event(instance, event_details)
                except Exception as e:
                    logger.warning(f"modify_tp failed: {e}")

            elif rule.trail_sl:
                try:
                    distance = evaluate_expr(rule.trail_sl.distance.expr, ctx)
                    event_details["action"] = "trail_sl"
                    event_details["distance"] = distance
                    if rule.trail_sl.step:
                        event_details["step"] = evaluate_expr(rule.trail_sl.step.expr, ctx)
                    await self._emit_management_event(instance, event_details)
                except Exception as e:
                    logger.warning(f"trail_sl failed: {e}")

            elif rule.partial_close:
                event_details["action"] = "partial_close"
                event_details["pct"] = rule.partial_close.pct
                await self._emit_management_event(instance, event_details)

            # Mark once-only rules as fired
            if rule.once:
                instance.state.fired_once_rules.append(rule.name)

    async def _emit_management_event(self, instance: PlaybookInstance, details: dict):
        """Emit a management event for the trade executor."""
        details["playbook_id"] = instance.playbook.id
        details["symbol"] = instance.symbol
        details["ticket"] = instance.state.open_ticket
        details["phase"] = instance.state.current_phase

        for cb in self._management_callbacks:
            try:
                result = cb(details)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(f"Management callback error: {e}")

    def _collect_indicators(
        self, symbol: str, config: PlaybookConfig
    ) -> dict[str, dict[str, float]]:
        """Collect current indicator values for all configured indicators."""
        result = {}
        for ind in config.indicators:
            cached = self.data_manager.get_cached_indicator(
                symbol, ind.timeframe, ind.id
            )
            if cached:
                result[ind.id] = cached.values
        return result

    def _collect_prev_indicators(
        self, symbol: str, config: PlaybookConfig
    ) -> dict[str, dict[str, float]]:
        """Collect previous bar's indicator values."""
        result = {}
        for ind in config.indicators:
            key = (symbol, ind.id)
            if key in self._prev_indicators:
                result[ind.id] = self._prev_indicators[key]
        return result

    def _update_prev_indicators(
        self,
        symbol: str,
        config: PlaybookConfig,
        current: dict[str, dict[str, float]],
    ):
        """Store current values as previous for next evaluation."""
        for ind_id, values in current.items():
            self._prev_indicators[(symbol, ind_id)] = dict(values)

    async def _get_trade_data(self, state: PlaybookState) -> dict[str, float] | None:
        """Get trade data for context from open ticket."""
        # This will be populated by the trade executor when a position is opened
        result = {}
        if state.open_ticket:
            result["ticket"] = float(state.open_ticket)
        for key in ("open_price", "sl", "tp", "lot", "pnl"):
            if key in state.variables:
                result[key] = float(state.variables[key])
        return result if result else None

    async def _persist_state(self, instance: PlaybookInstance):
        """Notify state change callbacks to persist state."""
        for cb in self._state_change_callbacks:
            try:
                result = cb(instance.state)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(f"State change callback error: {e}")

    def notify_trade_opened(
        self, playbook_id: int, ticket: int, direction: str, open_price: float, sl: float | None, tp: float | None, lot: float
    ):
        """Called by trade executor after a position is opened."""
        instance = self._instances.get(playbook_id)
        if not instance:
            return
        instance.state.open_ticket = ticket
        instance.state.open_direction = direction
        instance.state.variables["open_price"] = open_price
        instance.state.variables["lot"] = lot
        if sl is not None:
            instance.state.variables["sl"] = sl
        if tp is not None:
            instance.state.variables["tp"] = tp

    def notify_trade_closed(self, playbook_id: int, pnl: float | None = None):
        """Called by trade executor after a position is closed."""
        instance = self._instances.get(playbook_id)
        if not instance:
            return
        instance.state.open_ticket = None
        instance.state.open_direction = None

        # Circuit breaker: track consecutive losses
        if pnl is not None:
            if pnl < 0:
                instance.state.cb_consecutive_losses += 1
            else:
                instance.state.cb_consecutive_losses = 0
            self._check_circuit_breaker(instance)

        # Check on_trade_closed transition
        phase = instance.current_phase
        if phase and phase.on_trade_closed:
            instance.transition_to(phase.on_trade_closed.to)

    def notify_trade_error(self, playbook_id: int):
        """Called when a trade execution fails for this playbook."""
        instance = self._instances.get(playbook_id)
        if not instance:
            return
        instance.state.cb_error_count += 1
        self._check_circuit_breaker(instance)

    def _check_circuit_breaker(self, instance: "PlaybookInstance"):
        """Trip the circuit breaker if thresholds are exceeded."""
        from datetime import datetime
        cb = instance.config.risk.circuit_breaker
        state = instance.state

        if state.cb_tripped:
            return  # already tripped

        tripped = False
        reason = ""
        if cb.max_consecutive_losses > 0 and state.cb_consecutive_losses >= cb.max_consecutive_losses:
            tripped = True
            reason = f"{state.cb_consecutive_losses} consecutive losses"
        elif cb.max_errors > 0 and state.cb_error_count >= cb.max_errors:
            tripped = True
            reason = f"{state.cb_error_count} errors"

        if tripped:
            state.cb_tripped = True
            state.cb_tripped_at = datetime.now()
            logger.warning(
                f"CIRCUIT BREAKER TRIPPED for playbook {instance.config.name}: {reason}"
            )

    def is_circuit_breaker_active(self, playbook_id: int) -> bool:
        """Check if circuit breaker is currently active (tripped and not cooled down)."""
        from datetime import datetime
        instance = self._instances.get(playbook_id)
        if not instance:
            return False
        state = instance.state
        if not state.cb_tripped:
            return False
        # Check cooldown
        cb = instance.config.risk.circuit_breaker
        if cb.cooldown_minutes > 0 and state.cb_tripped_at:
            elapsed = (datetime.now() - state.cb_tripped_at).total_seconds() / 60
            if elapsed >= cb.cooldown_minutes:
                # Auto-reset
                state.cb_tripped = False
                state.cb_tripped_at = None
                state.cb_consecutive_losses = 0
                state.cb_error_count = 0
                logger.info(f"Circuit breaker auto-reset for playbook {instance.config.name} after {cb.cooldown_minutes}m cooldown")
                return False
        return True

    def reset_circuit_breaker(self, playbook_id: int) -> bool:
        """Manually reset the circuit breaker for a playbook."""
        instance = self._instances.get(playbook_id)
        if not instance:
            return False
        instance.state.cb_tripped = False
        instance.state.cb_tripped_at = None
        instance.state.cb_consecutive_losses = 0
        instance.state.cb_error_count = 0
        logger.info(f"Circuit breaker manually reset for playbook {instance.config.name}")
        return True
