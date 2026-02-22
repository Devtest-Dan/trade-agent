"""Shared test fixtures for backtest tests."""

import pytest
from agent.backtest.models import BacktestTrade


def make_trade(
    direction="BUY",
    open_idx=0,
    close_idx=10,
    open_price=2000.0,
    close_price=2010.0,
    open_time="2024-01-15T10:00:00",
    close_time="2024-01-15T14:00:00",
    sl=1990.0,
    tp=2020.0,
    lot=0.1,
    pnl=10.0,
    pnl_pips=10.0,
    commission=0.0,
    rr_achieved=1.0,
    outcome="win",
    exit_reason="tp",
    phase_at_entry="entry",
    market_regime="trending",
    fired_transition="",
    **kwargs,
) -> BacktestTrade:
    return BacktestTrade(
        direction=direction,
        open_idx=open_idx,
        close_idx=close_idx,
        open_price=open_price,
        close_price=close_price,
        open_time=open_time,
        close_time=close_time,
        sl=sl,
        tp=tp,
        lot=lot,
        pnl=pnl,
        pnl_pips=pnl_pips,
        commission=commission,
        rr_achieved=rr_achieved,
        outcome=outcome,
        exit_reason=exit_reason,
        phase_at_entry=phase_at_entry,
        market_regime=market_regime,
        fired_transition=fired_transition,
        **kwargs,
    )


@pytest.fixture
def winning_trades():
    """5 winning trades across 2 months."""
    return [
        make_trade(pnl=50.0, close_idx=10, open_idx=0, close_time="2024-01-10T12:00:00", direction="BUY"),
        make_trade(pnl=30.0, close_idx=15, open_idx=5, close_time="2024-01-20T12:00:00", direction="BUY"),
        make_trade(pnl=20.0, close_idx=25, open_idx=15, close_time="2024-02-05T12:00:00", direction="SELL"),
        make_trade(pnl=40.0, close_idx=35, open_idx=20, close_time="2024-02-15T12:00:00", direction="BUY"),
        make_trade(pnl=10.0, close_idx=40, open_idx=30, close_time="2024-02-25T12:00:00", direction="SELL"),
    ]


@pytest.fixture
def mixed_trades():
    """Mix of wins and losses for realistic metrics testing."""
    return [
        make_trade(pnl=50.0, outcome="win", close_idx=10, open_idx=0, close_time="2024-01-05T12:00:00", direction="BUY"),
        make_trade(pnl=-20.0, outcome="loss", close_idx=20, open_idx=10, close_time="2024-01-10T12:00:00", direction="BUY", exit_reason="sl"),
        make_trade(pnl=30.0, outcome="win", close_idx=30, open_idx=20, close_time="2024-01-15T12:00:00", direction="SELL"),
        make_trade(pnl=-15.0, outcome="loss", close_idx=45, open_idx=30, close_time="2024-01-20T12:00:00", direction="SELL", exit_reason="sl"),
        make_trade(pnl=-25.0, outcome="loss", close_idx=55, open_idx=45, close_time="2024-02-01T12:00:00", direction="BUY", exit_reason="sl"),
        make_trade(pnl=60.0, outcome="win", close_idx=65, open_idx=55, close_time="2024-02-10T12:00:00", direction="BUY"),
        make_trade(pnl=-10.0, outcome="loss", close_idx=75, open_idx=65, close_time="2024-02-15T12:00:00", direction="SELL", exit_reason="sl"),
        make_trade(pnl=35.0, outcome="win", close_idx=85, open_idx=75, close_time="2024-02-20T12:00:00", direction="BUY"),
    ]
