"""Tests for agent.backtest.metrics — backtest metrics computation."""

import pytest
from agent.backtest.metrics import (
    compute_drawdown_curve,
    compute_metrics,
    _compute_sortino,
    _compute_ulcer_index,
    _compute_skewness,
    _compute_kurtosis,
    _compute_streak_pnl,
    _compute_monthly_returns,
)
from tests.conftest import make_trade


# ── Drawdown curve ──────────────────────────────────────────────────

class TestDrawdownCurve:
    def test_empty(self):
        assert compute_drawdown_curve([]) == []

    def test_flat_equity(self):
        assert compute_drawdown_curve([100, 100, 100]) == [0, 0, 0]

    def test_always_rising(self):
        assert compute_drawdown_curve([100, 110, 120]) == [0, 0, 0]

    def test_simple_drawdown(self):
        dd = compute_drawdown_curve([100, 110, 90, 105])
        assert dd[0] == 0
        assert dd[1] == 0        # new peak
        assert dd[2] == -20      # 90 - 110
        assert dd[3] == -5       # 105 - 110

    def test_multi_peak(self):
        dd = compute_drawdown_curve([100, 120, 110, 130, 125])
        assert dd == [0, 0, -10, 0, -5]


# ── Sortino ratio ──────────────────────────────────────────────────

class TestSortino:
    def test_too_few_returns(self):
        assert _compute_sortino([10], 10) == 0.0

    def test_all_positive(self):
        # No downside deviation → large value
        result = _compute_sortino([10, 20, 15], 15)
        assert result == 999.0

    def test_all_negative(self):
        result = _compute_sortino([-10, -20, -15], -15)
        assert result < 0

    def test_mixed_returns(self):
        returns = [10, -5, 15, -10, 20]
        mean_ret = sum(returns) / len(returns)
        result = _compute_sortino(returns, mean_ret)
        assert result > 0  # positive mean, some downside


# ── Ulcer Index ────────────────────────────────────────────────────

class TestUlcerIndex:
    def test_too_few(self):
        assert _compute_ulcer_index([100]) == 0.0

    def test_no_drawdown(self):
        assert _compute_ulcer_index([100, 110, 120, 130]) == 0.0

    def test_with_drawdown(self):
        result = _compute_ulcer_index([100, 110, 90, 100])
        assert result > 0


# ── Skewness & Kurtosis ────────────────────────────────────────────

class TestDistribution:
    def test_skewness_too_few(self):
        assert _compute_skewness([1, 2]) == 0.0

    def test_skewness_symmetric(self):
        """Symmetric distribution → skewness ≈ 0."""
        vals = [-10, -5, 0, 5, 10]
        assert abs(_compute_skewness(vals)) < 0.01

    def test_skewness_right_skew(self):
        """Right-skewed data → positive skewness."""
        vals = [1, 2, 3, 4, 100]
        assert _compute_skewness(vals) > 0

    def test_kurtosis_too_few(self):
        assert _compute_kurtosis([1, 2, 3]) == 0.0

    def test_kurtosis_normal_ish(self):
        """Uniform-ish data → negative excess kurtosis (platykurtic)."""
        vals = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        k = _compute_kurtosis(vals)
        assert k < 0  # uniform is platykurtic

    def test_kurtosis_peaked(self):
        """Data with heavy tails → positive excess kurtosis."""
        vals = [0, 0, 0, 0, 0, 0, 100, -100]
        k = _compute_kurtosis(vals)
        assert k > 0

    def test_constant_values(self):
        """All identical values → zero variance → return 0."""
        assert _compute_skewness([5, 5, 5, 5]) == 0.0
        assert _compute_kurtosis([5, 5, 5, 5, 5]) == 0.0


# ── Streak P&L ─────────────────────────────────────────────────────

class TestStreakPnl:
    def test_empty(self):
        assert _compute_streak_pnl([]) == (0.0, 0.0)

    def test_all_wins(self):
        trades = [make_trade(pnl=10), make_trade(pnl=20), make_trade(pnl=30)]
        best, worst = _compute_streak_pnl(trades)
        assert best == 60.0  # all in one streak
        assert worst == 0.0

    def test_all_losses(self):
        trades = [make_trade(pnl=-10), make_trade(pnl=-20)]
        best, worst = _compute_streak_pnl(trades)
        assert best == 0.0
        assert worst == -30.0

    def test_mixed(self):
        trades = [
            make_trade(pnl=10),
            make_trade(pnl=20),
            make_trade(pnl=-5),
            make_trade(pnl=-15),
            make_trade(pnl=50),
        ]
        best, worst = _compute_streak_pnl(trades)
        assert best == 50.0   # last trade (single streak)
        assert worst == -20.0  # two consecutive losses


# ── Monthly returns ────────────────────────────────────────────────

class TestMonthlyReturns:
    def test_empty(self):
        assert _compute_monthly_returns([], 10000) == {}

    def test_grouping(self):
        trades = [
            make_trade(pnl=100, close_time="2024-01-15T12:00:00"),
            make_trade(pnl=-50, close_time="2024-01-20T12:00:00"),
            make_trade(pnl=200, close_time="2024-02-10T12:00:00"),
        ]
        result = _compute_monthly_returns(trades, 10000)
        assert "2024-01" in result
        assert "2024-02" in result
        assert result["2024-01"] == 0.5   # (100 - 50) / 10000 * 100
        assert result["2024-02"] == 2.0   # 200 / 10000 * 100

    def test_no_close_time(self):
        trades = [make_trade(pnl=100, close_time="")]
        assert _compute_monthly_returns(trades, 10000) == {}


# ── Full compute_metrics ───────────────────────────────────────────

class TestComputeMetrics:
    def test_empty_trades(self):
        m = compute_metrics([], [], 10000)
        assert m.total_trades == 0
        assert m.total_pnl == 0.0

    def test_all_wins(self, winning_trades):
        equity = [10000, 10050, 10080, 10100, 10140, 10150]
        m = compute_metrics(winning_trades, equity, 10000)
        assert m.total_trades == 5
        assert m.wins == 5
        assert m.losses == 0
        assert m.win_rate == 100.0
        assert m.total_pnl == 150.0
        assert m.profit_factor == 999.0  # no losses
        assert m.consecutive_wins == 5
        assert m.consecutive_losses == 0

    def test_mixed(self, mixed_trades):
        # Build simple equity curve
        equity = [10000.0]
        for t in mixed_trades:
            equity.append(equity[-1] + t.pnl)
        m = compute_metrics(mixed_trades, equity, 10000)

        assert m.total_trades == 8
        assert m.wins == 4
        assert m.losses == 4
        assert m.win_rate == 50.0
        total = sum(t.pnl for t in mixed_trades)
        assert m.total_pnl == round(total, 2)
        assert m.avg_win > 0
        assert m.avg_loss < 0
        assert m.sharpe_ratio != 0
        assert m.sortino_ratio != 0

    def test_directional_win_rates(self, mixed_trades):
        equity = [10000.0]
        for t in mixed_trades:
            equity.append(equity[-1] + t.pnl)
        m = compute_metrics(mixed_trades, equity, 10000)

        # BUY trades: pnl=[50, -20, -25, 60, 35] → 3 wins / 5 = 60%
        assert m.win_rate_long == 60.0
        # SELL trades: pnl=[30, -15, -10] → 1 win / 3 = 33.3%
        assert m.win_rate_short == pytest.approx(33.3, abs=0.1)

    def test_consecutive_streaks(self):
        trades = [
            make_trade(pnl=10),   # W
            make_trade(pnl=20),   # W
            make_trade(pnl=15),   # W
            make_trade(pnl=-5),   # L
            make_trade(pnl=-10),  # L
            make_trade(pnl=30),   # W
        ]
        equity = [10000.0]
        for t in trades:
            equity.append(equity[-1] + t.pnl)
        m = compute_metrics(trades, equity, 10000)
        assert m.consecutive_wins == 3
        assert m.consecutive_losses == 2

    def test_drawdown_metrics(self):
        trades = [make_trade(pnl=100), make_trade(pnl=-80)]
        equity = [10000, 10100, 10020]
        m = compute_metrics(trades, equity, 10000)
        assert m.max_drawdown == 80.0
        assert m.max_drawdown_pct > 0

    def test_single_trade(self):
        trades = [make_trade(pnl=25)]
        equity = [10000, 10025]
        m = compute_metrics(trades, equity, 10000)
        assert m.total_trades == 1
        assert m.wins == 1
        assert m.win_rate == 100.0
        assert m.sharpe_ratio == 0.0  # can't compute with 1 trade

    def test_avg_duration(self):
        trades = [
            make_trade(open_idx=0, close_idx=10, pnl=10),
            make_trade(open_idx=10, close_idx=30, pnl=-5),
        ]
        equity = [10000, 10010, 10005]
        m = compute_metrics(trades, equity, 10000)
        assert m.avg_duration_bars == 15.0  # (10 + 20) / 2

    def test_monthly_returns_populated(self, mixed_trades):
        equity = [10000.0]
        for t in mixed_trades:
            equity.append(equity[-1] + t.pnl)
        m = compute_metrics(mixed_trades, equity, 10000)
        assert len(m.monthly_returns) == 2  # Jan and Feb
        assert "2024-01" in m.monthly_returns
        assert "2024-02" in m.monthly_returns
