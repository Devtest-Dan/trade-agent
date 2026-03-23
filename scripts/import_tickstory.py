"""Import Tickstory CSV bar data into trade-agent bar cache."""
import asyncio
import csv
from datetime import datetime, timedelta
from agent.db.database import Database


async def import_bars(db, symbol: str, filepath: str):
    """Import M1 bars from Tickstory CSV and build M5/M15."""
    print(f"\n=== {symbol} ===")

    # Read CSV
    rows = []
    with open(filepath, "r") as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) < 7:
                continue
            try:
                dt = datetime.strptime(f"{row[0]} {row[1]}", "%Y%m%d %H:%M:%S")
                rows.append((
                    symbol, "M1", dt.isoformat(),
                    float(row[2]), float(row[3]), float(row[4]), float(row[5]),
                    float(row[6]), int(dt.timestamp())
                ))
            except (ValueError, IndexError):
                continue

    print(f"  Read {len(rows):,} M1 bars")

    # Insert M1
    batch_size = 10000
    for start in range(0, len(rows), batch_size):
        batch = rows[start:start + batch_size]
        await db._db.executemany(
            "INSERT OR IGNORE INTO bar_cache (symbol, timeframe, bar_time, open, high, low, close, volume, bar_time_unix) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            batch
        )
    await db._db.commit()
    print(f"  Cached M1")

    # Build M5 from M1
    m5_rows = []
    i = 0
    while i < len(rows):
        bar = rows[i]
        dt = datetime.fromisoformat(bar[2])
        aligned = dt.replace(minute=(dt.minute // 5) * 5, second=0, microsecond=0)
        end = aligned + timedelta(minutes=5)

        group = []
        while i < len(rows) and datetime.fromisoformat(rows[i][2]) < end:
            group.append(rows[i])
            i += 1

        if group:
            bt = aligned.isoformat()
            m5_rows.append((
                symbol, "M5", bt,
                group[0][3],  # open
                max(r[4] for r in group),  # high
                min(r[5] for r in group),  # low
                group[-1][6],  # close
                sum(r[7] for r in group),  # volume
                int(aligned.timestamp())
            ))

    for start in range(0, len(m5_rows), batch_size):
        batch = m5_rows[start:start + batch_size]
        await db._db.executemany(
            "INSERT OR IGNORE INTO bar_cache (symbol, timeframe, bar_time, open, high, low, close, volume, bar_time_unix) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            batch
        )
    await db._db.commit()
    print(f"  Built {len(m5_rows):,} M5 bars")

    # Build M15 from M1
    m15_rows = []
    i = 0
    while i < len(rows):
        bar = rows[i]
        dt = datetime.fromisoformat(bar[2])
        aligned = dt.replace(minute=(dt.minute // 15) * 15, second=0, microsecond=0)
        end = aligned + timedelta(minutes=15)

        group = []
        while i < len(rows) and datetime.fromisoformat(rows[i][2]) < end:
            group.append(rows[i])
            i += 1

        if group:
            bt = aligned.isoformat()
            m15_rows.append((
                symbol, "M15", bt,
                group[0][3], max(r[4] for r in group),
                min(r[5] for r in group), group[-1][6],
                sum(r[7] for r in group), int(aligned.timestamp())
            ))

    for start in range(0, len(m15_rows), batch_size):
        batch = m15_rows[start:start + batch_size]
        await db._db.executemany(
            "INSERT OR IGNORE INTO bar_cache (symbol, timeframe, bar_time, open, high, low, close, volume, bar_time_unix) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            batch
        )
    await db._db.commit()
    print(f"  Built {len(m15_rows):,} M15 bars")

    # Build H1 from M1
    h1_rows = []
    i = 0
    while i < len(rows):
        bar = rows[i]
        dt = datetime.fromisoformat(bar[2])
        aligned = dt.replace(minute=0, second=0, microsecond=0)
        end = aligned + timedelta(hours=1)

        group = []
        while i < len(rows) and datetime.fromisoformat(rows[i][2]) < end:
            group.append(rows[i])
            i += 1

        if group:
            bt = aligned.isoformat()
            h1_rows.append((
                symbol, "H1", bt,
                group[0][3], max(r[4] for r in group),
                min(r[5] for r in group), group[-1][6],
                sum(r[7] for r in group), int(aligned.timestamp())
            ))

    for start in range(0, len(h1_rows), batch_size):
        batch = h1_rows[start:start + batch_size]
        await db._db.executemany(
            "INSERT OR IGNORE INTO bar_cache (symbol, timeframe, bar_time, open, high, low, close, volume, bar_time_unix) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            batch
        )
    await db._db.commit()
    print(f"  Built {len(h1_rows):,} H1 bars")

    # Build H4 from M1
    h4_rows = []
    i = 0
    while i < len(rows):
        bar = rows[i]
        dt = datetime.fromisoformat(bar[2])
        aligned = dt.replace(hour=(dt.hour // 4) * 4, minute=0, second=0, microsecond=0)
        end = aligned + timedelta(hours=4)

        group = []
        while i < len(rows) and datetime.fromisoformat(rows[i][2]) < end:
            group.append(rows[i])
            i += 1

        if group:
            bt = aligned.isoformat()
            h4_rows.append((
                symbol, "H4", bt,
                group[0][3], max(r[4] for r in group),
                min(r[5] for r in group), group[-1][6],
                sum(r[7] for r in group), int(aligned.timestamp())
            ))

    for start in range(0, len(h4_rows), batch_size):
        batch = h4_rows[start:start + batch_size]
        await db._db.executemany(
            "INSERT OR IGNORE INTO bar_cache (symbol, timeframe, bar_time, open, high, low, close, volume, bar_time_unix) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            batch
        )
    await db._db.commit()
    print(f"  Built {len(h4_rows):,} H4 bars")


async def main():
    db = Database()
    await db.connect()

    data_dir = "D:/tickstory/History data"
    symbols = [
        ("GBPUSD", f"{data_dir}/GBPUSD_mt5_bars.csv"),
        ("USDJPY", f"{data_dir}/USDJPY_mt5_bars.csv"),
        ("EURJPY", f"{data_dir}/EURJPY_mt5_bars.csv"),
    ]

    for symbol, filepath in symbols:
        await import_bars(db, symbol, filepath)

    await db.disconnect()
    print("\nDone!")


if __name__ == "__main__":
    asyncio.run(main())
