"""Tests for agent.backtest.sweep — parameter sweep engine."""

import pytest
from agent.backtest.models import BacktestConfig, BacktestMetrics
from agent.backtest.sweep import (
    SweepParam,
    SweepRunResult,
    SweepResult,
    _apply_params,
)


@pytest.fixture
def playbook_config():
    """Minimal playbook config dict with variables and risk."""
    return {
        "name": "test_playbook",
        "symbols": ["XAUUSD"],
        "variables": {
            "rsi_threshold": {"default": 30, "type": "float"},
            "atr_multiplier": {"default": 1.5, "type": "float"},
        },
        "risk": {
            "max_lot": 0.5,
            "max_risk_pct": 2.0,
        },
        "indicators": [],
        "phases": {},
    }


@pytest.fixture
def bt_config():
    return BacktestConfig(
        playbook_id=1,
        symbol="XAUUSD",
        timeframe="H4",
        bar_count=500,
        spread_pips=0.3,
        starting_balance=10000.0,
    )


# ── _apply_params ──────────────────────────────────────────────────

class TestApplyParams:
    def test_variable_override(self, playbook_config, bt_config):
        pb, bt = _apply_params(playbook_config, bt_config, {"variables.rsi_threshold": 40.0})
        assert pb["variables"]["rsi_threshold"]["default"] == 40.0
        # Other variable unchanged
        assert pb["variables"]["atr_multiplier"]["default"] == 1.5

    def test_risk_override(self, playbook_config, bt_config):
        pb, bt = _apply_params(playbook_config, bt_config, {"risk.max_lot": 1.0})
        assert pb["risk"]["max_lot"] == 1.0

    def test_spread_override(self, playbook_config, bt_config):
        pb, bt = _apply_params(playbook_config, bt_config, {"spread_pips": 0.5})
        assert bt.spread_pips == 0.5

    def test_balance_override(self, playbook_config, bt_config):
        pb, bt = _apply_params(playbook_config, bt_config, {"starting_balance": 50000.0})
        assert bt.starting_balance == 50000.0

    def test_multiple_overrides(self, playbook_config, bt_config):
        params = {
            "variables.rsi_threshold": 25.0,
            "variables.atr_multiplier": 2.0,
            "risk.max_lot": 0.8,
            "spread_pips": 0.4,
        }
        pb, bt = _apply_params(playbook_config, bt_config, params)
        assert pb["variables"]["rsi_threshold"]["default"] == 25.0
        assert pb["variables"]["atr_multiplier"]["default"] == 2.0
        assert pb["risk"]["max_lot"] == 0.8
        assert bt.spread_pips == 0.4

    def test_unknown_variable_no_crash(self, playbook_config, bt_config):
        """Unknown variable should log warning but not crash."""
        pb, bt = _apply_params(playbook_config, bt_config, {"variables.nonexistent": 100.0})
        # Playbook unchanged
        assert "nonexistent" not in pb["variables"]

    def test_unknown_risk_field_no_crash(self, playbook_config, bt_config):
        pb, bt = _apply_params(playbook_config, bt_config, {"risk.nonexistent": 5.0})
        assert "nonexistent" not in pb["risk"]

    def test_unknown_path_no_crash(self, playbook_config, bt_config):
        pb, bt = _apply_params(playbook_config, bt_config, {"unknown.path": 1.0})
        # Should not crash

    def test_original_not_mutated(self, playbook_config, bt_config):
        """_apply_params should deep copy — original should not change."""
        original_default = playbook_config["variables"]["rsi_threshold"]["default"]
        _apply_params(playbook_config, bt_config, {"variables.rsi_threshold": 999.0})
        assert playbook_config["variables"]["rsi_threshold"]["default"] == original_default

    def test_bt_config_not_mutated(self, playbook_config, bt_config):
        """Backtest config should not be mutated (model_copy)."""
        original_spread = bt_config.spread_pips
        _apply_params(playbook_config, bt_config, {"spread_pips": 999.0})
        assert bt_config.spread_pips == original_spread


# ── SweepParam / SweepResult dataclasses ───────────────────────────

class TestDataclasses:
    def test_sweep_param(self):
        p = SweepParam(path="variables.rsi", values=[20, 30, 40])
        assert p.path == "variables.rsi"
        assert len(p.values) == 3

    def test_sweep_run_result(self):
        r = SweepRunResult(
            params={"variables.rsi": 30.0},
            metrics=BacktestMetrics(total_trades=10, wins=6, win_rate=60.0),
            trade_count=10,
        )
        assert r.params["variables.rsi"] == 30.0
        assert r.metrics.win_rate == 60.0

    def test_sweep_result(self):
        run1 = SweepRunResult(
            params={"a": 1},
            metrics=BacktestMetrics(total_pnl=100, sharpe_ratio=1.5),
            trade_count=5,
        )
        run2 = SweepRunResult(
            params={"a": 2},
            metrics=BacktestMetrics(total_pnl=200, sharpe_ratio=1.0),
            trade_count=8,
        )
        sr = SweepResult(
            total_combinations=2,
            completed=2,
            failed=0,
            duration_ms=150,
            runs=[run1, run2],
            best_by_sharpe=run1,
            best_by_pnl=run2,
        )
        assert sr.total_combinations == 2
        assert sr.best_by_sharpe.metrics.sharpe_ratio == 1.5
        assert sr.best_by_pnl.metrics.total_pnl == 200


# ── Combination generation ─────────────────────────────────────────

class TestCombinations:
    def test_cartesian_product(self):
        """Verify we get correct cartesian product of params."""
        import itertools
        params = [
            SweepParam(path="a", values=[1, 2]),
            SweepParam(path="b", values=[10, 20, 30]),
        ]
        combos = [
            dict(zip([p.path for p in params], combo))
            for combo in itertools.product(*[p.values for p in params])
        ]
        assert len(combos) == 6  # 2 * 3
        assert {"a": 1, "b": 10} in combos
        assert {"a": 2, "b": 30} in combos

    def test_single_param(self):
        import itertools
        params = [SweepParam(path="x", values=[1, 2, 3, 4, 5])]
        combos = [
            dict(zip([p.path for p in params], combo))
            for combo in itertools.product(*[p.values for p in params])
        ]
        assert len(combos) == 5

    def test_large_product(self):
        """3 params × 5 values each = 125 combinations."""
        import itertools
        params = [
            SweepParam(path="a", values=[1, 2, 3, 4, 5]),
            SweepParam(path="b", values=[10, 20, 30, 40, 50]),
            SweepParam(path="c", values=[0.1, 0.2, 0.3, 0.4, 0.5]),
        ]
        combos = list(itertools.product(*[p.values for p in params]))
        assert len(combos) == 125
