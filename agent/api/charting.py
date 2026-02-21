"""Charting API — candlestick data + indicator overlays + CSV/HST upload."""

import asyncio
import csv
import io
import struct
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from loguru import logger
from pydantic import BaseModel

from agent.api.main import app_state
from agent.backtest.bar_cache import load_bars, save_bars
from agent.backtest.indicators import OVERLAY_INDICATORS, OSCILLATOR_INDICATORS, IndicatorEngine
from agent.models.market import Bar

router = APIRouter(prefix="/api/chart", tags=["chart"])


class IndicatorRequest(BaseModel):
    name: str
    params: dict[str, Any] = {}


class ChartDataRequest(BaseModel):
    symbol: str
    timeframe: str
    count: int = 300
    indicators: list[IndicatorRequest] = []


@router.post("/data")
async def get_chart_data(req: ChartDataRequest):
    """Load bars from cache (or fetch from MT5) and compute indicator series."""
    db = app_state["db"]
    bridge = app_state["bridge"]
    mt5_connected = app_state.get("mt5_connected", False)

    # Load from cache
    bars = await load_bars(db, req.symbol, req.timeframe, req.count)

    # If not enough cached bars and MT5 is connected, fetch live
    if len(bars) < req.count and mt5_connected:
        try:
            fetched = await bridge.get_bars(req.symbol, req.timeframe, req.count)
            if fetched:
                await save_bars(db, fetched)
                bars = await load_bars(db, req.symbol, req.timeframe, req.count)
        except Exception as e:
            logger.warning(f"Failed to fetch bars from MT5: {e}")

    if not bars:
        raise HTTPException(status_code=404, detail=f"No bars available for {req.symbol} {req.timeframe}")

    # Format bars for response
    bar_data = [
        {
            "time": int(b.time.timestamp()),
            "open": b.open,
            "high": b.high,
            "low": b.low,
            "close": b.close,
            "volume": b.volume,
        }
        for b in bars
    ]

    # Compute indicators in thread executor to avoid blocking
    indicators_out: dict[str, Any] = {}
    if req.indicators:
        engine = IndicatorEngine(bars)
        loop = asyncio.get_event_loop()
        for ind in req.indicators:
            try:
                series = await loop.run_in_executor(
                    None, engine.compute_series, ind.name, ind.params
                )
                ind_type = "overlay" if ind.name in OVERLAY_INDICATORS else "oscillator"
                # Extract special _markers key (chart labels) if present
                markers = series.pop("_markers", None)
                entry: dict[str, Any] = {
                    "name": ind.name,
                    "params": ind.params,
                    "type": ind_type,
                    "outputs": series,
                }
                if markers:
                    entry["markers"] = markers
                indicators_out[f"{ind.name}_{_param_key(ind.params)}"] = entry
            except Exception as e:
                logger.warning(f"Failed to compute {ind.name}: {e}")

    return {
        "symbol": req.symbol,
        "timeframe": req.timeframe,
        "bars": bar_data,
        "indicators": indicators_out,
    }


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    symbol: str = Form(...),
    timeframe: str = Form(...),
):
    """Upload an MT4/MT5-exported CSV or HST file and cache the bars."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    ext = file.filename.lower().rsplit(".", 1)[-1] if "." in file.filename else ""
    if ext not in ("csv", "hst"):
        raise HTTPException(status_code=400, detail="File must be .csv or .hst")

    content = await file.read()

    if ext == "hst":
        bars = _parse_hst(content, symbol, timeframe)
        if not bars:
            raise HTTPException(status_code=400, detail="Could not parse any bars from HST file")
    else:
        text = content.decode("utf-8-sig", errors="replace")
        bars = _parse_mt5_csv(text, symbol, timeframe)
        if not bars:
            raise HTTPException(status_code=400, detail="Could not parse any bars from CSV")

    db = app_state["db"]
    await save_bars(db, bars)

    return {"bars_imported": len(bars), "symbol": symbol, "timeframe": timeframe}


def _param_key(params: dict) -> str:
    """Create a short key from indicator params (e.g. '14' or '12_26_9')."""
    if not params:
        return "default"
    vals = [str(v) for v in params.values()]
    return "_".join(vals)


def _parse_mt5_csv(text: str, symbol: str, timeframe: str) -> list[Bar]:
    """Parse common MT5 CSV export formats.

    Supports:
    - Tab-separated: <DATE>\t<TIME>\t<OPEN>\t<HIGH>\t<LOW>\t<CLOSE>\t<TICKVOL>\t<VOL>\t<SPREAD>
    - Comma-separated: Date,Time,Open,High,Low,Close,Volume
    - Auto-detects delimiter and date format
    """
    lines = text.strip().splitlines()
    if not lines:
        return []

    # Detect delimiter
    first_data = lines[1] if len(lines) > 1 else lines[0]
    delimiter = "\t" if "\t" in first_data else ","

    # Skip header if present
    reader = csv.reader(lines, delimiter=delimiter)
    rows = list(reader)
    if not rows:
        return []

    # Check if first row is a header
    start = 0
    first_row = rows[0]
    if first_row and any(h.lower() in ("date", "time", "open", "<date>") for h in first_row):
        start = 1

    bars: list[Bar] = []
    for row in rows[start:]:
        try:
            bar = _parse_row(row, symbol, timeframe)
            if bar:
                bars.append(bar)
        except Exception:
            continue

    # Sort by time ascending
    bars.sort(key=lambda b: b.time)
    return bars


def _parse_row(row: list[str], symbol: str, timeframe: str) -> Bar | None:
    """Parse a single CSV row into a Bar."""
    # Clean fields
    fields = [f.strip().strip("<>") for f in row]
    if len(fields) < 6:
        return None

    # Try different date+time formats
    dt = None
    # Format 1: separate date and time columns (most common MT5 export)
    for date_fmt in ("%Y.%m.%d", "%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y"):
        for time_fmt in ("%H:%M:%S", "%H:%M", ""):
            try:
                if time_fmt and len(fields) >= 7:
                    dt = datetime.strptime(f"{fields[0]} {fields[1]}", f"{date_fmt} {time_fmt}")
                    o, h, l, c = float(fields[2]), float(fields[3]), float(fields[4]), float(fields[5])
                    vol = float(fields[6]) if len(fields) > 6 else 0.0
                elif not time_fmt:
                    dt = datetime.strptime(fields[0], date_fmt)
                    o, h, l, c = float(fields[1]), float(fields[2]), float(fields[3]), float(fields[4])
                    vol = float(fields[5]) if len(fields) > 5 else 0.0
                break
            except (ValueError, IndexError):
                continue
        if dt:
            break

    if not dt:
        return None

    return Bar(
        symbol=symbol,
        timeframe=timeframe,
        time=dt,
        open=o,
        high=h,
        low=l,
        close=c,
        volume=vol,
    )


# MT4 period (minutes) to standard timeframe string
_PERIOD_MAP = {
    1: "M1", 5: "M5", 15: "M15", 30: "M30",
    60: "H1", 240: "H4", 1440: "D1", 10080: "W1", 43200: "MN",
}


def _parse_hst(data: bytes, symbol: str, timeframe: str) -> list[Bar]:
    """Parse MT4 HST (history) binary file.

    Supports both v400 and v401 formats.

    v400 header: 148 bytes
      int32  version (400)
      char64 copyright
      char12 symbol
      int32  period (minutes)
      int32  digits
      int32  timesign
      int32  last_sync
      int32[13] unused

    v400 records: 44 bytes each
      int32  time (unix)
      double open, low, high, close, volume

    v401 header: 148 bytes (same layout)
    v401 records: 60 bytes each
      int64  time (unix)
      double open, high, low, close
      int64  volume
      int32  spread
      int64  real_volume
    """
    HEADER_SIZE = 148

    if len(data) < HEADER_SIZE:
        logger.warning(f"HST file too small: {len(data)} bytes")
        return []

    # Parse header
    version = struct.unpack_from("<i", data, 0)[0]
    hst_symbol = struct.unpack_from("<12s", data, 68)[0].split(b"\x00")[0].decode("ascii", errors="replace")
    period = struct.unpack_from("<i", data, 80)[0]

    # Use symbol from HST header if form field is generic, otherwise prefer user input
    file_symbol = hst_symbol.strip()
    if file_symbol and symbol in ("XAUUSD", ""):
        symbol = file_symbol or symbol

    # Derive timeframe from period if not overridden
    file_tf = _PERIOD_MAP.get(period, timeframe)
    if timeframe in ("H1", ""):
        timeframe = file_tf

    logger.info(f"HST v{version}: symbol={file_symbol}, period={period} ({file_tf}), file size={len(data)} bytes")

    body = data[HEADER_SIZE:]
    bars: list[Bar] = []

    if version == 400:
        record_size = 44
        count = len(body) // record_size
        for i in range(count):
            offset = i * record_size
            if offset + record_size > len(body):
                break
            ts, o, low, high, c, vol = struct.unpack_from("<i5d", body, offset)
            dt = datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)
            bars.append(Bar(
                symbol=symbol, timeframe=timeframe, time=dt,
                open=o, high=high, low=low, close=c, volume=vol,
            ))

    elif version == 401:
        record_size = 60
        count = len(body) // record_size
        for i in range(count):
            offset = i * record_size
            if offset + record_size > len(body):
                break
            ts, o, high, low, c, vol, spread, real_vol = struct.unpack_from("<q4dqiq", body, offset)
            dt = datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)
            bars.append(Bar(
                symbol=symbol, timeframe=timeframe, time=dt,
                open=o, high=high, low=low, close=c, volume=float(vol),
            ))

    else:
        logger.warning(f"Unknown HST version: {version}")
        return []

    bars.sort(key=lambda b: b.time)
    logger.info(f"Parsed {len(bars)} bars from HST file")
    return bars
