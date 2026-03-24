"""Import market data from Yahoo Finance into trade-agent bar cache.

Supports stocks, ETFs, crypto, indices. Builds M5/M15/H1/H4 from
the finest available data (typically 1m for last 30 days, 1h for older).

Usage:
    python -m scripts.import_yfinance AAPL TSLA MSFT SPY QQQ BTC-USD ETH-USD
    python -m scripts.import_yfinance --interval 1h --period 2y AAPL  # longer history
"""
import asyncio
import sys
from datetime import datetime, timedelta

import yfinance as yf

from agent.db.database import Database


def _aggregate_bars(rows: list[tuple], target_minutes: int, symbol: str, tf_label: str) -> list[tuple]:
    """Aggregate M1/lower bars into higher timeframe bars."""
    if not rows:
        return []

    result = []
    i = 0
    while i < len(rows):
        dt = datetime.fromisoformat(rows[i][2])

        if target_minutes < 60:
            aligned = dt.replace(minute=(dt.minute // target_minutes) * target_minutes, second=0, microsecond=0)
        elif target_minutes == 60:
            aligned = dt.replace(minute=0, second=0, microsecond=0)
        elif target_minutes == 240:
            aligned = dt.replace(hour=(dt.hour // 4) * 4, minute=0, second=0, microsecond=0)
        else:
            aligned = dt.replace(minute=0, second=0, microsecond=0)

        end = aligned + timedelta(minutes=target_minutes)

        group = []
        while i < len(rows) and datetime.fromisoformat(rows[i][2]) < end:
            group.append(rows[i])
            i += 1

        if group:
            bt = aligned.isoformat()
            result.append((
                symbol, tf_label, bt,
                group[0][3],  # open
                max(r[4] for r in group),  # high
                min(r[5] for r in group),  # low
                group[-1][6],  # close
                sum(r[7] for r in group),  # volume
                int(aligned.timestamp())
            ))

    return result


async def import_symbol(db, symbol: str, interval: str = "1m", period: str = "30d"):
    """Import a single symbol from yfinance."""
    print(f"\n=== {symbol} ===")

    ticker = yf.Ticker(symbol)

    # Download data
    print(f"  Downloading {period} of {interval} data...")
    df = ticker.history(period=period, interval=interval)

    if df.empty:
        print(f"  No data returned for {symbol}")
        return

    print(f"  Got {len(df):,} bars")

    # Determine source timeframe
    interval_map = {
        "1m": ("M1", 1), "2m": ("M2", 2), "5m": ("M5", 5),
        "15m": ("M15", 15), "30m": ("M30", 30),
        "60m": ("H1", 60), "1h": ("H1", 60),
        "1d": ("D1", 1440), "1wk": ("W1", 10080),
    }
    src_tf, src_minutes = interval_map.get(interval, ("M1", 1))

    # Convert DataFrame to row tuples
    rows = []
    for idx, row in df.iterrows():
        dt = idx.to_pydatetime()
        if dt.tzinfo:
            dt = dt.replace(tzinfo=None)
        rows.append((
            symbol, src_tf, dt.isoformat(),
            float(row["Open"]), float(row["High"]),
            float(row["Low"]), float(row["Close"]),
            float(row.get("Volume", 0)),
            int(dt.timestamp())
        ))

    # Insert source timeframe
    batch_size = 10000
    for start in range(0, len(rows), batch_size):
        batch = rows[start:start + batch_size]
        await db._db.executemany(
            "INSERT OR IGNORE INTO bar_cache (symbol, timeframe, bar_time, open, high, low, close, volume, bar_time_unix) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            batch
        )
    await db._db.commit()
    print(f"  Cached {len(rows):,} {src_tf} bars")

    # Build higher timeframes from source
    targets = []
    if src_minutes <= 1:
        targets = [("M5", 5), ("M15", 15), ("H1", 60), ("H4", 240)]
    elif src_minutes <= 5:
        targets = [("M15", 15), ("H1", 60), ("H4", 240)]
    elif src_minutes <= 15:
        targets = [("H1", 60), ("H4", 240)]
    elif src_minutes <= 60:
        targets = [("H4", 240)]

    for tf_label, tf_minutes in targets:
        agg = _aggregate_bars(rows, tf_minutes, symbol, tf_label)
        for start in range(0, len(agg), batch_size):
            batch = agg[start:start + batch_size]
            await db._db.executemany(
                "INSERT OR IGNORE INTO bar_cache (symbol, timeframe, bar_time, open, high, low, close, volume, bar_time_unix) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                batch
            )
        await db._db.commit()
        print(f"  Built {len(agg):,} {tf_label} bars")


async def main():
    symbols = sys.argv[1:] if len(sys.argv) > 1 else [
        "AAPL", "TSLA", "MSFT", "NVDA", "AMZN",  # Tech stocks
        "SPY", "QQQ",  # ETFs
        "BTC-USD", "ETH-USD",  # Crypto
    ]

    # Check for flags
    interval = "1m"
    period = "30d"
    clean_symbols = []
    i = 0
    while i < len(symbols):
        if symbols[i] == "--interval" and i + 1 < len(symbols):
            interval = symbols[i + 1]
            i += 2
        elif symbols[i] == "--period" and i + 1 < len(symbols):
            period = symbols[i + 1]
            i += 2
        else:
            clean_symbols.append(symbols[i])
            i += 1
    symbols = clean_symbols

    db = Database()
    await db.connect()

    for symbol in symbols:
        try:
            await import_symbol(db, symbol, interval=interval, period=period)
        except Exception as e:
            print(f"  ERROR: {e}")

    # Also fetch longer history at 1h for deeper backtests
    if interval == "1m":
        print("\n--- Fetching 2y hourly history for deeper backtests ---")
        for symbol in symbols:
            try:
                await import_symbol(db, symbol, interval="1h", period="2y")
            except Exception as e:
                print(f"  ERROR on {symbol} 1h: {e}")

    await db.disconnect()
    print("\nDone!")


if __name__ == "__main__":
    asyncio.run(main())
