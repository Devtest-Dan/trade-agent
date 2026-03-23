"""Portfolio backtest — merge multiple symbol backtests into a single equity curve."""

import asyncio
import json
from datetime import datetime
from agent.db.database import Database
from agent.models.playbook import PlaybookConfig
from agent.backtest.engine import BacktestEngine
from agent.backtest.indicators import MultiTFIndicatorEngine, _tf_to_minutes
from agent.backtest.bar_cache import load_bars
from agent.backtest.models import BacktestConfig


async def run_portfolio_backtest(
    configs: list[dict],
    starting_balance: float = 10000.0,
    max_drawdown_pct: float = 30.0,
):
    """
    Run multiple backtests and merge trades into a single portfolio equity curve.

    configs: list of dicts with keys:
        playbook_id, symbol, timeframe, bar_count, spread_pips, slippage_pips
    """
    db = Database()
    await db.connect()

    all_trades = []

    for cfg in configs:
        playbook = await db.get_playbook(cfg["playbook_id"])
        if not playbook:
            print(f"  Playbook {cfg['playbook_id']} not found, skipping")
            continue

        pc = playbook.config
        symbol = cfg["symbol"]
        timeframe = cfg["timeframe"]
        bar_count = cfg["bar_count"]

        print(f"  Running {symbol} (playbook {cfg['playbook_id']}, lot {pc.risk.max_lot})...")

        # Load bars for all required timeframes
        primary_min = _tf_to_minutes(timeframe)
        total_minutes = bar_count * primary_min

        tfs = {timeframe.upper()}
        for ind in pc.indicators:
            if ind.timeframe:
                tfs.add(ind.timeframe.upper())

        tf_bars = {}
        for tf in tfs:
            if tf == timeframe.upper():
                needed = bar_count
            else:
                needed = int((total_minutes / _tf_to_minutes(tf)) * 1.2) + 50
            needed = max(needed, 60)
            bars = await load_bars(db, symbol, tf, needed)
            tf_bars[tf] = bars

        if not tf_bars.get(timeframe.upper()) or len(tf_bars[timeframe.upper()]) < 60:
            print(f"    Not enough bars for {symbol} {timeframe}, skipping")
            continue

        # Run backtest
        indicator_engine = MultiTFIndicatorEngine()
        for tf, bars in tf_bars.items():
            indicator_engine.add_timeframe(tf, bars)
        indicator_engine.precompute(pc.indicators)

        bt_config = BacktestConfig(
            playbook_id=cfg["playbook_id"],
            symbol=symbol,
            timeframe=timeframe,
            bar_count=bar_count,
            spread_pips=cfg.get("spread_pips", 0.2),
            slippage_pips=cfg.get("slippage_pips", 0.1),
            commission_per_lot=cfg.get("commission_per_lot", 0.0),
            starting_balance=starting_balance,
        )
        engine = BacktestEngine(
            playbook=pc,
            bars=tf_bars[timeframe.upper()],
            indicator_engine=indicator_engine,
            config=bt_config,
        )
        result = engine.run()

        for t in result.trades:
            trade = t.model_dump() if hasattr(t, "model_dump") else t.__dict__.copy()
            trade["_symbol"] = symbol
            trade["_lot_size"] = pc.risk.max_lot
            all_trades.append(trade)

        print(f"    {symbol}: {len(result.trades)} trades, PnL ${sum(t.pnl for t in result.trades):+,.2f}")

    await db.disconnect()

    if not all_trades:
        print("\nNo trades generated across any symbol.")
        return

    # Sort all trades by close_time (when PnL is realized)
    for t in all_trades:
        if isinstance(t.get("close_time"), str):
            t["close_time"] = datetime.fromisoformat(t["close_time"])
        if isinstance(t.get("open_time"), str):
            t["open_time"] = datetime.fromisoformat(t["open_time"])

    all_trades.sort(key=lambda t: t["close_time"])

    # Build portfolio equity curve
    balance = starting_balance
    peak = balance
    max_dd = 0
    max_dd_pct_actual = 0
    equity_curve = [balance]
    monthly_pnl = {}
    symbol_stats = {}
    consecutive_losses = 0
    max_consecutive_losses = 0
    consecutive_wins = 0
    max_consecutive_wins = 0
    winning_trades = []
    losing_trades = []

    # Track overlapping positions
    open_positions = []  # trades sorted by open_time that haven't closed yet

    for trade in all_trades:
        pnl = trade["pnl"]
        symbol = trade["_symbol"]
        close_time = trade["close_time"]

        # Update balance
        balance += pnl
        equity_curve.append(balance)

        # Track peak and drawdown
        if balance > peak:
            peak = balance
        dd = peak - balance
        dd_pct = (dd / peak * 100) if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd
        if dd_pct > max_dd_pct_actual:
            max_dd_pct_actual = dd_pct

        # Monthly tracking
        month_key = close_time.strftime("%Y-%m")
        monthly_pnl[month_key] = monthly_pnl.get(month_key, 0) + pnl

        # Per-symbol stats
        if symbol not in symbol_stats:
            symbol_stats[symbol] = {"trades": 0, "wins": 0, "pnl": 0, "lot": trade["_lot_size"]}
        symbol_stats[symbol]["trades"] += 1
        symbol_stats[symbol]["pnl"] += pnl

        # Win/loss tracking
        if pnl > 0:
            winning_trades.append(pnl)
            symbol_stats[symbol]["wins"] += 1
            consecutive_wins += 1
            consecutive_losses = 0
            if consecutive_wins > max_consecutive_wins:
                max_consecutive_wins = consecutive_wins
        else:
            losing_trades.append(pnl)
            consecutive_losses += 1
            consecutive_wins = 0
            if consecutive_losses > max_consecutive_losses:
                max_consecutive_losses = consecutive_losses

    # Check for overlapping positions (trades open at the same time)
    overlap_count = 0
    for i, t1 in enumerate(all_trades):
        for t2 in all_trades[i+1:]:
            if t2["open_time"] < t1["close_time"]:
                overlap_count += 1
            else:
                break

    # Calculate metrics
    total_trades = len(all_trades)
    total_wins = len(winning_trades)
    total_losses = len(losing_trades)
    total_pnl = balance - starting_balance
    win_rate = (total_wins / total_trades * 100) if total_trades else 0
    avg_win = sum(winning_trades) / len(winning_trades) if winning_trades else 0
    avg_loss = sum(losing_trades) / len(losing_trades) if losing_trades else 0
    gross_wins = sum(winning_trades)
    gross_losses = abs(sum(losing_trades))
    profit_factor = gross_wins / gross_losses if gross_losses > 0 else float("inf")
    expectancy = total_pnl / total_trades if total_trades else 0
    recovery_factor = total_pnl / max_dd if max_dd > 0 else float("inf")

    # Print report
    print("\n" + "=" * 60)
    print("PORTFOLIO BACKTEST — SHARED $10,000 ACCOUNT")
    print("=" * 60)

    print("\nPER-SYMBOL BREAKDOWN")
    print("-" * 60)
    for sym, stats in sorted(symbol_stats.items()):
        wr = (stats["wins"] / stats["trades"] * 100) if stats["trades"] else 0
        print(f"  {sym:8s} (lot {stats['lot']})  {stats['trades']:>3} trades | WR {wr:>5.1f}% | ${stats['pnl']:>+10,.2f}")

    print(f"\nPORTFOLIO METRICS")
    print("-" * 60)
    print(f"  Starting Balance:     ${starting_balance:>10,.2f}")
    print(f"  Ending Balance:       ${balance:>10,.2f}")
    print(f"  Total PnL:            ${total_pnl:>+10,.2f}")
    print(f"  Return:               {total_pnl/starting_balance*100:>+9.1f}%")
    print(f"  Total Trades:         {total_trades:>10}")
    print(f"  Wins / Losses:        {total_wins:>4}W / {total_losses}L")
    print(f"  Win Rate:             {win_rate:>9.1f}%")
    print(f"  Profit Factor:        {profit_factor:>10.2f}")
    print(f"  Avg Win:              ${avg_win:>+10,.2f}")
    print(f"  Avg Loss:             ${avg_loss:>+10,.2f}")
    print(f"  Win/Loss Ratio:       {abs(avg_win/avg_loss) if avg_loss else 0:>10.2f}")
    print(f"  Expectancy/Trade:     ${expectancy:>+10,.2f}")
    print(f"  Max Drawdown:         ${max_dd:>10,.2f} ({max_dd_pct_actual:.1f}%)")
    print(f"  Recovery Factor:      {recovery_factor:>10.2f}")
    print(f"  Max Consec Wins:      {max_consecutive_wins:>10}")
    print(f"  Max Consec Losses:    {max_consecutive_losses:>10}")
    print(f"  Overlapping Trades:   {overlap_count:>10}")

    print(f"\nMONTHLY RETURNS")
    print("-" * 60)
    win_months = 0
    for month in sorted(monthly_pnl.keys()):
        pnl_val = monthly_pnl[month]
        pct = pnl_val / starting_balance * 100
        sign = "+" if pnl_val >= 0 else ""
        if pnl_val > 0:
            win_months += 1
        print(f"  {month}:  {sign}${pnl_val:>8,.2f}  ({sign}{pct:.1f}%)")

    print(f"\n  Profitable Months:    {win_months}/{len(monthly_pnl)} ({win_months/len(monthly_pnl)*100:.0f}%)")
    print(f"  Best Month:           ${max(monthly_pnl.values()):>+10,.2f}")
    print(f"  Worst Month:          ${min(monthly_pnl.values()):>+10,.2f}")
    avg_monthly = sum(monthly_pnl.values()) / len(monthly_pnl)
    print(f"  Avg Monthly PnL:      ${avg_monthly:>+10,.2f} ({avg_monthly/starting_balance*100:+.1f}%)")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    configs = [
        # Trend Continuation (M5 RSI + re-entry)
        {
            "playbook_id": 14,
            "symbol": "EURUSD",
            "timeframe": "M5",
            "bar_count": 60000,
            "spread_pips": 0.2,
            "slippage_pips": 0.1,
        },
        {
            "playbook_id": 14,
            "symbol": "GBPJPY",
            "timeframe": "M5",
            "bar_count": 60000,
            "spread_pips": 2.0,
            "slippage_pips": 0.3,
        },
        {
            "playbook_id": 15,
            "symbol": "XAUUSD",
            "timeframe": "M5",
            "bar_count": 60000,
            "spread_pips": 3.0,
            "slippage_pips": 0.5,
        },
        # Mean Reversion (per-symbol optimized)
        {
            "playbook_id": 22,
            "symbol": "EURUSD",
            "timeframe": "M5",
            "bar_count": 60000,
            "spread_pips": 0.2,
            "slippage_pips": 0.1,
        },
        {
            "playbook_id": 23,
            "symbol": "GBPJPY",
            "timeframe": "M5",
            "bar_count": 60000,
            "spread_pips": 2.0,
            "slippage_pips": 0.3,
        },
        {
            "playbook_id": 24,
            "symbol": "XAUUSD",
            "timeframe": "M5",
            "bar_count": 60000,
            "spread_pips": 3.0,
            "slippage_pips": 0.5,
        },
    ]

    asyncio.run(run_portfolio_backtest(configs, starting_balance=10000.0))
