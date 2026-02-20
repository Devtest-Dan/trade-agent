"""Bar cache — fetch OHLCV from MT5 and cache in SQLite."""

from datetime import datetime
from loguru import logger

from agent.models.market import Bar


async def save_bars(db, bars: list[Bar]):
    """Upsert bars into bar_cache table."""
    if not bars:
        return
    for bar in bars:
        await db._db.execute(
            """INSERT INTO bar_cache (symbol, timeframe, bar_time, open, high, low, close, volume, fetched_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(symbol, timeframe, bar_time) DO UPDATE SET
                 open = excluded.open, high = excluded.high, low = excluded.low,
                 close = excluded.close, volume = excluded.volume, fetched_at = excluded.fetched_at""",
            (
                bar.symbol,
                bar.timeframe,
                bar.time.isoformat(),
                bar.open,
                bar.high,
                bar.low,
                bar.close,
                bar.volume,
                datetime.now().isoformat(),
            ),
        )
    await db._db.commit()
    logger.info(f"Cached {len(bars)} bars for {bars[0].symbol} {bars[0].timeframe}")


async def load_bars(db, symbol: str, timeframe: str, count: int = 500) -> list[Bar]:
    """Load bars from cache, ordered oldest first."""
    cursor = await db._db.execute(
        """SELECT * FROM bar_cache
           WHERE symbol = ? AND timeframe = ?
           ORDER BY bar_time DESC LIMIT ?""",
        (symbol, timeframe, count),
    )
    rows = await cursor.fetchall()
    bars = [
        Bar(
            symbol=row["symbol"],
            timeframe=row["timeframe"],
            time=datetime.fromisoformat(row["bar_time"]),
            open=row["open"],
            high=row["high"],
            low=row["low"],
            close=row["close"],
            volume=row["volume"],
        )
        for row in reversed(rows)  # oldest first
    ]
    return bars


async def get_cached_bar_count(db, symbol: str, timeframe: str) -> int:
    """Get number of cached bars."""
    cursor = await db._db.execute(
        "SELECT COUNT(*) as cnt FROM bar_cache WHERE symbol = ? AND timeframe = ?",
        (symbol, timeframe),
    )
    row = await cursor.fetchone()
    return row["cnt"] if row else 0


async def fetch_and_cache(bridge, db, symbol: str, timeframe: str, count: int = 500) -> list[Bar]:
    """Fetch bars from MT5, cache them, return the list."""
    bars = await bridge.get_bars(symbol, timeframe, count)
    if bars:
        await save_bars(db, bars)
    return bars
