"""Import Manager — background import of large historical data files.

Supports tick CSV, bar CSV, and HST binary formats.
Tick CSVs are aggregated to OHLCV bars at the specified timeframe.
Uses producer-consumer architecture for constant-memory streaming.
"""

import asyncio
import csv
import os
import struct
import uuid
from datetime import datetime, timezone
from typing import Any

from loguru import logger

from agent.backtest.bar_cache import BATCH_SIZE, _UPSERT_SQL, _bar_to_tuple
from agent.backtest.indicators import _TF_MINUTES
from agent.models.market import Bar


def _tf_to_seconds(tf: str) -> int:
    """Convert timeframe string to seconds."""
    minutes = _TF_MINUTES.get(tf.upper())
    if minutes is None:
        raise ValueError(f"Unknown timeframe: {tf}")
    return minutes * 60


def detect_format(file_path: str) -> str:
    """Auto-detect file format: 'hst', 'bar_csv', or 'tick_csv'.

    - HST: binary file with version 400 or 401 header
    - bar_csv: 6+ columns (date, time, O, H, L, C, V)
    - tick_csv: 4-5 columns (timestamp, bid, ask, [volume])
    """
    with open(file_path, "rb") as f:
        header = f.read(256)

    # HST binary check — first 4 bytes are int version (400 or 401)
    if len(header) >= 148:
        version = struct.unpack_from("<i", header, 0)[0]
        if version in (400, 401):
            return "hst"

    # CSV detection — read first few data lines
    try:
        with open(file_path, "r", encoding="utf-8-sig", errors="replace") as f:
            lines = []
            for i, line in enumerate(f):
                lines.append(line.strip())
                if i >= 10:
                    break

        if not lines:
            return "bar_csv"

        # Find first data line (skip potential header)
        for line in lines:
            if not line:
                continue
            delimiter = "\t" if "\t" in line else ","
            fields = line.split(delimiter)
            # Skip header-like lines
            if any(h.lower().strip("<>") in ("date", "time", "open", "bid") for h in fields[:3]):
                continue
            num_fields = len(fields)
            if num_fields >= 6:
                return "bar_csv"
            elif num_fields >= 3:
                return "tick_csv"
            break
    except Exception:
        pass

    return "bar_csv"


class ImportManager:
    """Manages background data import jobs."""

    def __init__(self):
        self._jobs: dict[str, dict[str, Any]] = {}

    def start_import(
        self,
        db,
        file_path: str,
        symbol: str,
        timeframe: str,
        fmt: str = "auto",
        price_mode: str = "bid",
    ) -> str:
        """Start a background import job. Returns job_id."""
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        if fmt == "auto":
            fmt = detect_format(file_path)

        file_size = os.path.getsize(file_path)
        job_id = uuid.uuid4().hex[:12]
        job: dict[str, Any] = {
            "id": job_id,
            "status": "pending",
            "file_path": file_path,
            "symbol": symbol.upper(),
            "timeframe": timeframe.upper(),
            "format": fmt,
            "price_mode": price_mode,
            "file_size": file_size,
            "bytes_processed": 0,
            "bars_imported": 0,
            "started_at": datetime.now().isoformat(),
            "completed_at": None,
            "error": None,
            "cancel_requested": False,
        }
        self._jobs[job_id] = job

        # Launch background task
        asyncio.create_task(self._run_import(db, job))
        return job_id

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        return self._jobs.get(job_id)

    def cancel_job(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if not job or job["status"] not in ("pending", "importing"):
            return False
        job["cancel_requested"] = True
        return True

    def list_jobs(self) -> list[dict[str, Any]]:
        return list(self._jobs.values())

    async def _run_import(self, db, job: dict[str, Any]):
        """Run the import in background using producer-consumer pattern."""
        job["status"] = "importing"
        fmt = job["format"]
        file_path = job["file_path"]
        symbol = job["symbol"]
        timeframe = job["timeframe"]
        price_mode = job["price_mode"]

        queue: asyncio.Queue = asyncio.Queue(maxsize=4)
        total_bars = 0

        try:
            # Producer: read file in executor thread, put bar batches on queue
            loop = asyncio.get_event_loop()

            if fmt == "tick_csv":
                producer_fn = lambda: self._produce_tick_csv(
                    file_path, symbol, timeframe, price_mode, job, queue, loop
                )
            elif fmt == "bar_csv":
                producer_fn = lambda: self._produce_bar_csv(
                    file_path, symbol, timeframe, job, queue, loop
                )
            elif fmt == "hst":
                producer_fn = lambda: self._produce_hst(
                    file_path, symbol, timeframe, job, queue, loop
                )
            else:
                raise ValueError(f"Unknown format: {fmt}")

            producer_task = loop.run_in_executor(None, producer_fn)

            # Consumer: pull batches from queue, write to DB
            now_iso = datetime.now().isoformat()
            while True:
                batch = await queue.get()
                if batch is None:
                    break  # Producer done

                if job["cancel_requested"]:
                    job["status"] = "cancelled"
                    break

                # Convert bars to tuples and upsert
                tuples = [_bar_to_tuple(b, now_iso) for b in batch]
                await db._db.executemany(_UPSERT_SQL, tuples)
                await db._db.commit()
                total_bars += len(batch)
                job["bars_imported"] = total_bars

            # Wait for producer to finish
            await producer_task

            if job["status"] == "importing":
                job["status"] = "complete"

        except Exception as e:
            job["status"] = "error"
            job["error"] = str(e)
            logger.error(f"Import job {job['id']} failed: {e}")

        job["bars_imported"] = total_bars
        job["completed_at"] = datetime.now().isoformat()
        logger.info(f"Import job {job['id']}: {job['status']} — {total_bars} bars")

    def _produce_tick_csv(
        self, file_path: str, symbol: str, timeframe: str,
        price_mode: str, job: dict, queue: asyncio.Queue, loop,
    ):
        """Producer thread: parse tick CSV, aggregate to bars, put batches on queue."""
        tf_seconds = _tf_to_seconds(timeframe)
        batch: list[Bar] = []

        # Current bar state
        bar_open_ts = 0
        bar_o = bar_h = bar_l = bar_c = 0.0
        bar_vol = 0
        line_count = 0

        try:
            with open(file_path, "r", encoding="utf-8-sig", errors="replace", buffering=8 * 1024 * 1024) as f:
                reader = csv.reader(f)
                for row in reader:
                    if job["cancel_requested"]:
                        break

                    line_count += 1
                    # Update progress every 100K lines
                    if line_count % 100_000 == 0:
                        job["bytes_processed"] = f.tell()

                    # Skip header
                    if line_count == 1:
                        fields = [c.strip().lower().strip("<>") for c in row]
                        if any(h in ("date", "time", "datetime", "timestamp", "bid") for h in fields):
                            continue

                    # Parse tick row: various formats
                    # Common: timestamp, bid, ask [, volume]
                    # Or: date, time, bid, ask [, volume]
                    try:
                        tick_ts, price = self._parse_tick_row(row, price_mode)
                    except Exception:
                        continue

                    if tick_ts is None:
                        continue

                    # Bucket into bar
                    bucket_ts = (tick_ts // tf_seconds) * tf_seconds

                    if bucket_ts != bar_open_ts:
                        # Emit previous bar
                        if bar_open_ts > 0:
                            bar = Bar(
                                symbol=symbol, timeframe=timeframe,
                                time=datetime.fromtimestamp(bar_open_ts, tz=timezone.utc).replace(tzinfo=None),
                                open=bar_o, high=bar_h, low=bar_l, close=bar_c,
                                volume=float(bar_vol),
                            )
                            batch.append(bar)
                            if len(batch) >= BATCH_SIZE:
                                future = asyncio.run_coroutine_threadsafe(queue.put(batch), loop)
                                future.result()
                                batch = []

                        # Start new bar
                        bar_open_ts = bucket_ts
                        bar_o = bar_h = bar_l = bar_c = price
                        bar_vol = 1
                    else:
                        # Update current bar
                        if price > bar_h:
                            bar_h = price
                        if price < bar_l:
                            bar_l = price
                        bar_c = price
                        bar_vol += 1

                # Flush last bar
                if bar_open_ts > 0:
                    bar = Bar(
                        symbol=symbol, timeframe=timeframe,
                        time=datetime.fromtimestamp(bar_open_ts, tz=timezone.utc).replace(tzinfo=None),
                        open=bar_o, high=bar_h, low=bar_l, close=bar_c,
                        volume=float(bar_vol),
                    )
                    batch.append(bar)

                # Flush remaining batch
                if batch:
                    future = asyncio.run_coroutine_threadsafe(queue.put(batch), loop)
                    future.result()

                job["bytes_processed"] = job["file_size"]

        except Exception as e:
            logger.error(f"Tick CSV producer error: {e}")
            raise
        finally:
            # Signal consumer we're done
            future = asyncio.run_coroutine_threadsafe(queue.put(None), loop)
            future.result()

    def _parse_tick_row(self, row: list[str], price_mode: str) -> tuple[int | None, float]:
        """Parse a tick CSV row. Returns (unix_timestamp, price)."""
        fields = [f.strip() for f in row]
        if len(fields) < 3:
            return None, 0.0

        # Try parsing timestamp
        ts = None
        bid_idx = 1
        ask_idx = 2

        # Format: unix_timestamp, bid, ask
        try:
            val = float(fields[0])
            if val > 1e9:  # Unix timestamp
                ts = int(val)
            elif val > 1e6:  # Unix timestamp in ms
                ts = int(val / 1000)
        except ValueError:
            pass

        # Format: date time, bid, ask  or  date, time, bid, ask
        if ts is None:
            for date_fmt in ("%Y.%m.%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y.%m.%d %H:%M:%S.%f",
                             "%Y-%m-%dT%H:%M:%S", "%Y/%m/%d %H:%M:%S"):
                try:
                    dt = datetime.strptime(fields[0], date_fmt)
                    ts = int(dt.replace(tzinfo=timezone.utc).timestamp())
                    break
                except ValueError:
                    continue

        # Try date + time in separate columns
        if ts is None and len(fields) >= 4:
            for date_fmt in ("%Y.%m.%d", "%Y-%m-%d", "%Y/%m/%d"):
                for time_fmt in ("%H:%M:%S", "%H:%M:%S.%f", "%H:%M"):
                    try:
                        dt = datetime.strptime(f"{fields[0]} {fields[1]}", f"{date_fmt} {time_fmt}")
                        ts = int(dt.replace(tzinfo=timezone.utc).timestamp())
                        bid_idx = 2
                        ask_idx = 3
                        break
                    except ValueError:
                        continue
                if ts is not None:
                    break

        if ts is None:
            return None, 0.0

        bid = float(fields[bid_idx])
        ask = float(fields[ask_idx]) if ask_idx < len(fields) else bid

        if price_mode == "mid":
            price = (bid + ask) / 2
        elif price_mode == "ask":
            price = ask
        else:
            price = bid

        return ts, price

    def _produce_bar_csv(
        self, file_path: str, symbol: str, timeframe: str,
        job: dict, queue: asyncio.Queue, loop,
    ):
        """Producer thread: parse bar CSV, put batches on queue."""
        from agent.api.charting import _parse_row

        batch: list[Bar] = []
        line_count = 0
        header_skipped = False

        try:
            with open(file_path, "r", encoding="utf-8-sig", errors="replace", buffering=8 * 1024 * 1024) as f:
                reader = csv.reader(f, delimiter="\t")

                # Peek first line to detect delimiter
                first_line = f.readline()
                f.seek(0)
                delimiter = "\t" if "\t" in first_line else ","
                reader = csv.reader(f, delimiter=delimiter)

                for row in reader:
                    if job["cancel_requested"]:
                        break

                    line_count += 1
                    if line_count % 100_000 == 0:
                        job["bytes_processed"] = f.tell()

                    # Skip header
                    if not header_skipped:
                        header_skipped = True
                        if any(h.lower().strip("<>") in ("date", "time", "open") for h in row[:3]):
                            continue

                    try:
                        bar = _parse_row(row, symbol, timeframe)
                        if bar:
                            batch.append(bar)
                            if len(batch) >= BATCH_SIZE:
                                future = asyncio.run_coroutine_threadsafe(queue.put(batch), loop)
                                future.result()
                                batch = []
                    except Exception:
                        continue

                if batch:
                    future = asyncio.run_coroutine_threadsafe(queue.put(batch), loop)
                    future.result()

                job["bytes_processed"] = job["file_size"]

        except Exception as e:
            logger.error(f"Bar CSV producer error: {e}")
            raise
        finally:
            future = asyncio.run_coroutine_threadsafe(queue.put(None), loop)
            future.result()

    def _produce_hst(
        self, file_path: str, symbol: str, timeframe: str,
        job: dict, queue: asyncio.Queue, loop,
    ):
        """Producer thread: parse HST binary file, put batches on queue."""
        HEADER_SIZE = 148
        _PERIOD_MAP = {
            1: "M1", 5: "M5", 15: "M15", 30: "M30",
            60: "H1", 240: "H4", 1440: "D1", 10080: "W1", 43200: "MN",
        }

        batch: list[Bar] = []

        try:
            with open(file_path, "rb") as f:
                header = f.read(HEADER_SIZE)
                if len(header) < HEADER_SIZE:
                    raise ValueError("HST file too small")

                version = struct.unpack_from("<i", header, 0)[0]
                hst_symbol = struct.unpack_from("<12s", header, 68)[0].split(b"\x00")[0].decode("ascii", errors="replace").strip()
                period = struct.unpack_from("<i", header, 80)[0]

                # Use symbol/timeframe from HST if available
                if hst_symbol:
                    symbol = hst_symbol
                file_tf = _PERIOD_MAP.get(period, timeframe)
                timeframe = file_tf

                if version == 400:
                    record_size = 44
                elif version == 401:
                    record_size = 60
                else:
                    raise ValueError(f"Unknown HST version: {version}")

                # Read and parse in chunks
                while not job["cancel_requested"]:
                    chunk = f.read(record_size * BATCH_SIZE)
                    if not chunk:
                        break

                    job["bytes_processed"] = f.tell()
                    count = len(chunk) // record_size

                    for i in range(count):
                        offset = i * record_size
                        if offset + record_size > len(chunk):
                            break

                        if version == 400:
                            ts, o, low, high, c, vol = struct.unpack_from("<i5d", chunk, offset)
                        else:
                            ts, o, high, low, c, vol, _, _ = struct.unpack_from("<q4dqiq", chunk, offset)

                        dt = datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)
                        bar = Bar(
                            symbol=symbol, timeframe=timeframe, time=dt,
                            open=o, high=high, low=low, close=c, volume=float(vol),
                        )
                        batch.append(bar)

                    if len(batch) >= BATCH_SIZE:
                        future = asyncio.run_coroutine_threadsafe(queue.put(batch[:BATCH_SIZE]), loop)
                        future.result()
                        batch = batch[BATCH_SIZE:]

                if batch:
                    future = asyncio.run_coroutine_threadsafe(queue.put(batch), loop)
                    future.result()

                job["bytes_processed"] = job["file_size"]

        except Exception as e:
            logger.error(f"HST producer error: {e}")
            raise
        finally:
            future = asyncio.run_coroutine_threadsafe(queue.put(None), loop)
            future.result()
