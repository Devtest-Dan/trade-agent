"""Charting API — candlestick data + indicator overlays + CSV upload."""

import asyncio
import csv
import io
from datetime import datetime
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from loguru import logger
from pydantic import BaseModel

from agent.api.main import app_state
from agent.backtest.bar_cache import load_bars, save_bars
from agent.backtest.indicators import OVERLAY_INDICATORS, OSCILLATOR_INDICATORS, IndicatorEngine
from agent.models.market import Bar

router = APIRouter(prefix="/chart", tags=["chart"])


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
                indicators_out[f"{ind.name}_{_param_key(ind.params)}"] = {
                    "name": ind.name,
                    "params": ind.params,
                    "type": ind_type,
                    "outputs": series,
                }
            except Exception as e:
                logger.warning(f"Failed to compute {ind.name}: {e}")

    return {
        "symbol": req.symbol,
        "timeframe": req.timeframe,
        "bars": bar_data,
        "indicators": indicators_out,
    }


@router.post("/upload")
async def upload_csv(
    file: UploadFile = File(...),
    symbol: str = Form(...),
    timeframe: str = Form(...),
):
    """Upload an MT5-exported CSV file and cache the bars."""
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be a .csv")

    content = await file.read()
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
