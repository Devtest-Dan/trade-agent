"""Bar cache — fetch OHLCV from MT5 and cache in SQLite."""

from datetime import datetime
from loguru import logger

from agent.models.market import Bar

BATCH_SIZE = 10_000

_UPSERT_SQL = """INSERT INTO bar_cache
    (symbol, timeframe, bar_time, bar_time_unix, open, high, low, close, volume, fetched_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(symbol, timeframe, bar_time) DO UPDATE SET
      open = excluded.open, high = excluded.high, low = excluded.low,
      close = excluded.close, volume = excluded.volume,
      bar_time_unix = excluded.bar_time_unix, fetched_at = excluded.fetched_at"""


def _bar_to_tuple(bar: Bar, now_iso: str) -> tuple:
    ts = int(bar.time.timestamp()) if bar.time else 0
    return (
        bar.symbol, bar.timeframe, bar.time.isoformat(), ts,
        bar.open, bar.high, bar.low, bar.close, bar.volume, now_iso,
    )


async def save_bars(db, bars: list[Bar]):
    """Upsert bars into bar_cache table using batch executemany()."""
    if not bars:
        return
    now_iso = datetime.now().isoformat()
    tuples = [_bar_to_tuple(b, now_iso) for b in bars]

    # Insert in chunks to keep memory bounded
    for i in range(0, len(tuples), BATCH_SIZE):
        chunk = tuples[i : i + BATCH_SIZE]
        await db._db.executemany(_UPSERT_SQL, chunk)

    await db._db.commit()
    logger.info(f"Cached {len(bars)} bars for {bars[0].symbol} {bars[0].timeframe}")


async def save_bars_streaming(db, bars_iter, symbol: str, timeframe: str) -> int:
    """Save bars from an iterator/generator in streaming batches. Returns count."""
    now_iso = datetime.now().isoformat()
    total = 0
    batch: list[tuple] = []

    for bar in bars_iter:
        batch.append(_bar_to_tuple(bar, now_iso))
        if len(batch) >= BATCH_SIZE:
            await db._db.executemany(_UPSERT_SQL, batch)
            await db._db.commit()
            total += len(batch)
            batch = []

    if batch:
        await db._db.executemany(_UPSERT_SQL, batch)
        await db._db.commit()
        total += len(batch)

    if total:
        logger.info(f"Cached {total} bars for {symbol} {timeframe} (streaming)")
    return total


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


async def cleanup_old_bars(db, retention_days: int):
    """Delete bars older than retention_days. No-op if retention_days <= 0."""
    if retention_days <= 0:
        return 0
    cutoff = datetime.now().timestamp() - (retention_days * 86400)
    cursor = await db._db.execute(
        "DELETE FROM bar_cache WHERE bar_time_unix < ? AND bar_time_unix IS NOT NULL",
        (int(cutoff),),
    )
    await db._db.commit()
    deleted = cursor.rowcount
    if deleted:
        logger.info(f"Cleaned up {deleted} bars older than {retention_days} days")
    return deleted


async def fetch_and_cache(bridge, db, symbol: str, timeframe: str, count: int = 500) -> list[Bar]:
    """Fetch bars from MT5, cache them, return the list."""
    bars = await bridge.get_bars(symbol, timeframe, count)
    if bars:
        await save_bars(db, bars)
    return bars
