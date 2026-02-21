"""Data Import API — import large historical data files and manage bar cache."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agent.api.main import app_state

router = APIRouter(prefix="/api/data", tags=["data"])


class ImportRequest(BaseModel):
    file_path: str
    symbol: str
    timeframe: str
    format: str = "auto"
    price_mode: str = "bid"


@router.post("/import")
async def start_import(req: ImportRequest):
    """Start a background import job for a local data file."""
    db = app_state["db"]
    manager = app_state["import_manager"]
    try:
        job_id = manager.start_import(
            db,
            file_path=req.file_path,
            symbol=req.symbol,
            timeframe=req.timeframe,
            fmt=req.format,
            price_mode=req.price_mode,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"job_id": job_id, "status": "pending"}


@router.get("/import/{job_id}")
async def get_import_job(job_id: str):
    """Poll import job progress."""
    manager = app_state["import_manager"]
    job = manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/import/{job_id}/cancel")
async def cancel_import(job_id: str):
    """Cancel a running import job."""
    manager = app_state["import_manager"]
    ok = manager.cancel_job(job_id)
    if not ok:
        raise HTTPException(status_code=400, detail="Job not found or not running")
    return {"status": "cancelling"}


@router.get("/imports")
async def list_imports():
    """List all import jobs."""
    manager = app_state["import_manager"]
    return manager.list_jobs()


@router.get("/summary")
async def data_summary():
    """Get summary of all cached bar data: symbol, timeframe, count, date range."""
    db = app_state["db"]
    cursor = await db._db.execute(
        """SELECT symbol, timeframe,
                  COUNT(*) as bar_count,
                  MIN(bar_time) as first_date,
                  MAX(bar_time) as last_date
           FROM bar_cache
           GROUP BY symbol, timeframe
           ORDER BY symbol, timeframe"""
    )
    rows = await cursor.fetchall()
    return [
        {
            "symbol": row["symbol"],
            "timeframe": row["timeframe"],
            "bar_count": row["bar_count"],
            "first_date": row["first_date"],
            "last_date": row["last_date"],
        }
        for row in rows
    ]


@router.delete("/bars")
async def delete_bars(symbol: str, timeframe: str):
    """Delete all cached bars for a symbol/timeframe pair."""
    db = app_state["db"]
    cursor = await db._db.execute(
        "DELETE FROM bar_cache WHERE symbol = ? AND timeframe = ?",
        (symbol.upper(), timeframe.upper()),
    )
    await db._db.commit()
    return {"deleted": cursor.rowcount, "symbol": symbol.upper(), "timeframe": timeframe.upper()}
