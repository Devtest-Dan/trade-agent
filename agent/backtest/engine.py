"""Core backtest engine — replays playbook logic over historical bars."""

from typing import Any

from loguru import logger

from agent.backtest.indicators import IndicatorEngine, MultiTFIndicatorEngine
from agent.backtest.metrics import compute_metrics, compute_drawdown_curve
from agent.backtest.models import BacktestConfig, BacktestResult, BacktestTrade
from agent.models.market import Bar
from agent.models.playbook import PlaybookConfig
from agent.playbook_eval import ExpressionContext, evaluate_condition, evaluate_expr


class BacktestEngine:
    """Replay a playbook over historical bars."""

    def __init__(
        self,
        playbook: PlaybookConfig,
        bars: list[Bar],
        indicator_engine: IndicatorEngine | MultiTFIndicatorEngine,
        config: BacktestConfig,
    ):
        self.playbook = playbook
        self.bars = bars
        self.config = config
        self.half_spread = config.spread_pips * _pip_value(config.symbol)
        self.slippage = config.slippage_pips * _pip_value(config.symbol)
        self.commission_per_lot = config.commission_per_lot

        # Accept either engine type; auto-wrap plain IndicatorEngine
        if isinstance(indicator_engine, MultiTFIndicatorEngine):
            self._multi = indicator_engine
        else:
            self._multi = MultiTFIndicatorEngine()
            self._multi.add_timeframe(config.timeframe, bars)
            self._multi.precompute(playbook.indicators)

    def run(self) -> BacktestResult:
        """Run the backtest synchronously. Returns full result."""
        # Initialize state
        current_phase = self.playbook.initial_phase
        variables: dict[str, Any] = {
            k: v.default for k, v in self.playbook.variables.items()
        }
        bars_in_phase = 0
        fired_once_rules: list[str] = []

        # Position state
        position_open = False
        position_direction = ""
        position_open_idx = 0
        position_open_price = 0.0
        position_sl: float | None = None
        position_tp: float | None = None
        position_lot = self.playbook.risk.max_lot
        position_phase_at_entry = ""
        position_vars_at_entry: dict = {}
        position_indicators_at_entry: dict = {}

        trades: list[BacktestTrade] = []
        equity = self.config.starting_balance
        equity_curve = [equity]

        prev_indicators: dict[str, dict[str, float]] = {}

        # Adaptive warmup: based on max indicator period + buffer
        warmup = _compute_warmup(self.playbook.indicators, len(self.bars))

        for bar_idx in range(warmup, len(self.bars)):
            bar = self.bars[bar_idx]

            # Compute all playbook indicators at current bar
            indicators = self._compute_indicators(bar_idx)

            # Build expression context
            ctx = ExpressionContext(
                indicators=indicators,
                prev_indicators=prev_indicators,
                variables=variables,
                price=bar.close,
                trade={
                    "open_price": position_open_price,
                    "sl": position_sl or 0.0,
                    "tp": position_tp or 0.0,
                    "lot": position_lot,
                    "pnl": self._calc_unrealized_pnl(position_direction, position_open_price, bar.close, position_lot) if position_open else 0.0,
                } if position_open else {},
                risk={
                    "max_lot": self.playbook.risk.max_lot,
                    "max_daily_trades": float(self.playbook.risk.max_daily_trades),
                    "max_drawdown_pct": self.playbook.risk.max_drawdown_pct,
                },
            )

            bars_in_phase += 1

            # Check SL/TP hit on open position FIRST
            if position_open:
                closed, trade = self._check_sl_tp(
                    bar, bar_idx, position_direction, position_open_idx,
                    position_open_price, position_sl, position_tp, position_lot,
                    position_phase_at_entry, position_vars_at_entry, position_indicators_at_entry,
                )
                if closed:
                    trades.append(trade)
                    equity += trade.pnl
                    position_open = False

                    # on_trade_closed transition
                    phase_obj = self.playbook.phases.get(current_phase)
                    if phase_obj and phase_obj.on_trade_closed:
                        current_phase = phase_obj.on_trade_closed.to
                        bars_in_phase = 0
                        fired_once_rules = []

            # Check phase timeout
            phase_obj = self.playbook.phases.get(current_phase)
            if phase_obj and phase_obj.timeout:
                if bars_in_phase >= phase_obj.timeout.bars:
                    current_phase = phase_obj.timeout.to
                    bars_in_phase = 0
                    fired_once_rules = []

            # Evaluate transitions (sorted by priority descending)
            phase_obj = self.playbook.phases.get(current_phase)
            if phase_obj:
                sorted_transitions = sorted(
                    phase_obj.transitions, key=lambda t: t.priority, reverse=True
                )
                for trans in sorted_transitions:
                    try:
                        if evaluate_condition(trans.conditions.model_dump(), ctx):
                            # Execute actions
                            for action in trans.actions:
                                if action.set_var and action.expr:
                                    try:
                                        variables[action.set_var] = evaluate_expr(action.expr, ctx)
                                    except Exception:
                                        pass

                                if action.open_trade and not position_open:
                                    td = action.open_trade
                                    direction = td.direction
                                    lot = position_lot
                                    if td.lot:
                                        try:
                                            lot = evaluate_expr(td.lot.expr, ctx)
                                        except Exception:
                                            lot = self.playbook.risk.max_lot

                                    sl_val = None
                                    tp_val = None
                                    if td.sl:
                                        try:
                                            sl_val = evaluate_expr(td.sl.expr, ctx)
                                        except Exception:
                                            pass
                                    if td.tp:
                                        try:
                                            tp_val = evaluate_expr(td.tp.expr, ctx)
                                        except Exception:
                                            pass

                                    # Open position with spread + slippage (adverse)
                                    if direction == "BUY":
                                        open_price = bar.close + self.half_spread + self.slippage
                                    else:
                                        open_price = bar.close - self.half_spread - self.slippage

                                    position_open = True
                                    position_direction = direction
                                    position_open_idx = bar_idx
                                    position_open_price = open_price
                                    position_sl = sl_val
                                    position_tp = tp_val
                                    position_lot = lot
                                    position_phase_at_entry = current_phase
                                    position_vars_at_entry = dict(variables)
                                    position_indicators_at_entry = {
                                        k: dict(v) for k, v in indicators.items()
                                    }

                                if action.close_trade and position_open:
                                    trade = self._close_position(
                                        bar, bar_idx, position_direction, position_open_idx,
                                        position_open_price, position_sl, position_tp, position_lot,
                                        "transition", position_phase_at_entry,
                                        position_vars_at_entry, position_indicators_at_entry,
                                    )
                                    trades.append(trade)
                                    equity += trade.pnl
                                    position_open = False

                            # Phase transition
                            current_phase = trans.to
                            bars_in_phase = 0
                            fired_once_rules = []
                            break
                    except Exception as e:
                        logger.debug(f"Transition eval error at bar {bar_idx}: {e}")
                        continue

                # Position management rules (if still in same phase and position open)
                if position_open and phase_obj:
                    for rule in phase_obj.position_management:
                        if rule.once and rule.name in fired_once_rules:
                            continue
                        try:
                            if evaluate_condition(rule.when.model_dump(), ctx):
                                if rule.modify_sl and position_open:
                                    try:
                                        new_sl = evaluate_expr(rule.modify_sl.expr, ctx)
                                        position_sl = new_sl
                                    except Exception:
                                        pass

                                if rule.modify_tp and position_open:
                                    try:
                                        new_tp = evaluate_expr(rule.modify_tp.expr, ctx)
                                        position_tp = new_tp
                                    except Exception:
                                        pass

                                if rule.trail_sl and position_open:
                                    try:
                                        distance = evaluate_expr(rule.trail_sl.distance.expr, ctx)
                                        if position_direction == "BUY":
                                            new_sl = bar.close - distance
                                            if position_sl is None or new_sl > position_sl:
                                                position_sl = new_sl
                                        else:
                                            new_sl = bar.close + distance
                                            if position_sl is None or new_sl < position_sl:
                                                position_sl = new_sl
                                    except Exception:
                                        pass

                                if rule.once:
                                    fired_once_rules.append(rule.name)
                        except Exception:
                            continue

            # Update equity curve
            unrealized = 0.0
            if position_open:
                unrealized = self._calc_unrealized_pnl(
                    position_direction, position_open_price, bar.close, position_lot
                )
            equity_curve.append(equity + unrealized)

            prev_indicators = {k: dict(v) for k, v in indicators.items()}

        # Close any remaining position at end of data
        if position_open:
            trade = self._close_position(
                self.bars[-1], len(self.bars) - 1,
                position_direction, position_open_idx,
                position_open_price, position_sl, position_tp, position_lot,
                "end_of_data", position_phase_at_entry,
                position_vars_at_entry, position_indicators_at_entry,
            )
            trades.append(trade)
            equity += trade.pnl
            equity_curve[-1] = equity

        # Compute metrics
        metrics = compute_metrics(trades, equity_curve, self.config.starting_balance)
        dd_curve = compute_drawdown_curve(equity_curve)

        return BacktestResult(
            config=self.config,
            metrics=metrics,
            equity_curve=equity_curve,
            drawdown_curve=dd_curve,
            trades=trades,
        )

    def _compute_indicators(self, bar_idx: int) -> dict[str, dict[str, float]]:
        """Look up precomputed indicator values at a given bar index (O(1))."""
        result = {}
        for ind_cfg in self.playbook.indicators:
            result[ind_cfg.id] = self._multi.get_at(
                ind_cfg.id, bar_idx, self.config.timeframe, ind_cfg.timeframe
            )
        return result

    def _check_sl_tp(
        self, bar: Bar, bar_idx: int, direction: str, open_idx: int,
        open_price: float, sl: float | None, tp: float | None, lot: float,
        phase: str, vars_entry: dict, ind_entry: dict,
    ) -> tuple[bool, BacktestTrade | None]:
        """Check if SL or TP was hit on this bar. Conservative: if both hit, assume SL."""
        sl_hit = False
        tp_hit = False

        if direction == "BUY":
            if sl is not None and bar.low <= sl:
                sl_hit = True
            if tp is not None and bar.high >= tp:
                tp_hit = True
        else:  # SELL
            if sl is not None and bar.high >= sl:
                sl_hit = True
            if tp is not None and bar.low <= tp:
                tp_hit = True

        if sl_hit:
            close_price = sl
            exit_reason = "sl"
        elif tp_hit:
            close_price = tp
            exit_reason = "tp"
        else:
            return False, None

        trade = self._make_trade(
            direction, open_idx, bar_idx, open_price, close_price,
            sl, tp, lot, exit_reason, phase, vars_entry, ind_entry,
        )
        return True, trade

    def _close_position(
        self, bar: Bar, bar_idx: int, direction: str, open_idx: int,
        open_price: float, sl: float | None, tp: float | None, lot: float,
        exit_reason: str, phase: str, vars_entry: dict, ind_entry: dict,
    ) -> BacktestTrade:
        """Close position at current bar close."""
        if direction == "BUY":
            close_price = bar.close - self.half_spread - self.slippage
        else:
            close_price = bar.close + self.half_spread + self.slippage
        return self._make_trade(
            direction, open_idx, bar_idx, open_price, close_price,
            sl, tp, lot, exit_reason, phase, vars_entry, ind_entry,
        )

    def _make_trade(
        self, direction: str, open_idx: int, close_idx: int,
        open_price: float, close_price: float,
        sl: float | None, tp: float | None, lot: float,
        exit_reason: str, phase: str, vars_entry: dict, ind_entry: dict,
    ) -> BacktestTrade:
        """Create a BacktestTrade with computed PnL."""
        raw_pnl = self._calc_pnl(direction, open_price, close_price, lot)
        commission = round(self.commission_per_lot * lot, 2)
        pnl = raw_pnl - commission
        pnl_pips = self._calc_pips(direction, open_price, close_price)

        # R:R achieved
        rr = None
        if sl is not None and sl != open_price:
            risk_distance = abs(open_price - sl)
            if risk_distance > 0:
                reward_distance = close_price - open_price if direction == "BUY" else open_price - close_price
                rr = round(reward_distance / risk_distance, 2)

        # Outcome
        if pnl > 0:
            outcome = "win"
        elif pnl < 0:
            outcome = "loss"
        else:
            outcome = "breakeven"

        open_time = self.bars[open_idx].time.isoformat() if open_idx < len(self.bars) else ""
        close_time = self.bars[close_idx].time.isoformat() if close_idx < len(self.bars) else ""

        return BacktestTrade(
            direction=direction,
            open_idx=open_idx,
            close_idx=close_idx,
            open_price=round(open_price, 5),
            close_price=round(close_price, 5),
            open_time=open_time,
            close_time=close_time,
            sl=round(sl, 5) if sl is not None else None,
            tp=round(tp, 5) if tp is not None else None,
            lot=lot,
            pnl=round(pnl, 2),
            pnl_pips=round(pnl_pips, 1),
            commission=commission,
            rr_achieved=rr,
            outcome=outcome,
            exit_reason=exit_reason,
            phase_at_entry=phase,
            variables_at_entry=vars_entry,
            entry_indicators=ind_entry,
        )

    def _calc_pnl(self, direction: str, open_price: float, close_price: float, lot: float) -> float:
        """Calculate P&L in account currency."""
        pip_val = _pip_value(self.config.symbol)
        if direction == "BUY":
            pips = (close_price - open_price) / pip_val
        else:
            pips = (open_price - close_price) / pip_val
        # Standard lot value per pip (approximate)
        pip_dollar = _pip_dollar_value(self.config.symbol, lot)
        return pips * pip_dollar

    def _calc_unrealized_pnl(self, direction: str, open_price: float, current_price: float, lot: float) -> float:
        return self._calc_pnl(direction, open_price, current_price, lot)

    def _calc_pips(self, direction: str, open_price: float, close_price: float) -> float:
        pip_val = _pip_value(self.config.symbol)
        if direction == "BUY":
            return (close_price - open_price) / pip_val
        else:
            return (open_price - close_price) / pip_val


def _pip_value(symbol: str) -> float:
    """Get pip size for a symbol."""
    symbol = symbol.upper()
    if "JPY" in symbol:
        return 0.01
    if "XAU" in symbol:
        return 0.1  # Gold: 1 pip = $0.10
    if "XAG" in symbol:
        return 0.01
    if "BTC" in symbol or "ETH" in symbol:
        return 1.0
    # Default forex
    return 0.0001


def _compute_warmup(indicators: list, total_bars: int) -> int:
    """Compute adaptive warmup period based on max indicator period.

    Looks at common period-related params (period, length, slow_period, etc.)
    across all indicators. Uses max_period + 20% buffer, clamped between 20
    and 25% of total bars.
    """
    PERIOD_KEYS = {"period", "length", "slow_period", "slow_length", "long_period", "timeperiod", "lookback", "bars_back"}
    max_period = 0
    for ind in indicators:
        params = ind.params if hasattr(ind, "params") else {}
        for key, val in params.items():
            if key.lower() in PERIOD_KEYS:
                try:
                    max_period = max(max_period, int(val))
                except (ValueError, TypeError):
                    pass
        # MACD has fast/slow/signal params
        if hasattr(ind, "name") and ind.name.upper() == "MACD":
            slow = params.get("slow", params.get("slow_period", 26))
            signal = params.get("signal", params.get("signal_period", 9))
            try:
                max_period = max(max_period, int(slow) + int(signal))
            except (ValueError, TypeError):
                pass

    # Default minimum if no period-based indicators found
    if max_period < 20:
        max_period = 20

    # Add 20% buffer for indicator stabilization
    warmup = int(max_period * 1.2)

    # Clamp: at least 20, at most 25% of bars
    warmup = max(20, min(warmup, total_bars // 4))
    return warmup


def _pip_dollar_value(symbol: str, lot: float) -> float:
    """Approximate dollar value per pip per lot."""
    symbol = symbol.upper()
    if "XAU" in symbol:
        return lot * 100 * 0.1  # 1 lot gold = 100 oz, pip = $0.10 → $10/pip/lot
    if "XAG" in symbol:
        return lot * 5000 * 0.01
    if "JPY" in symbol:
        return lot * 100000 * 0.01 / 100  # approximate
    # Default forex: 1 lot = 100k units, pip = 0.0001
    return lot * 100000 * 0.0001
