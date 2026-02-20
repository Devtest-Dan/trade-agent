"""Indicators API routes — list, upload, poll, view/edit code, delete."""

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from loguru import logger

from agent.api.auth import get_current_user
from agent.api.main import app_state
from agent.indicators.custom import (
    discover_custom_indicators,
    list_custom_catalog_entries,
    delete_custom_indicator,
    get_custom_indicator_dir,
)

router = APIRouter(prefix="/api/indicators", tags=["indicators"])

BUILTIN_CATALOG_PATH = Path(__file__).parent.parent / "indicators" / "catalog.json"


def _load_builtin_catalog() -> list[dict]:
    if BUILTIN_CATALOG_PATH.exists():
        return json.loads(BUILTIN_CATALOG_PATH.read_text(encoding="utf-8"))
    return []


@router.get("")
async def list_indicators(user: str = Depends(get_current_user)):
    """List all indicators (built-in + custom)."""
    builtin = _load_builtin_catalog()
    for entry in builtin:
        entry["source"] = "builtin"

    custom = list_custom_catalog_entries()
    for entry in custom:
        entry["source"] = "custom"

    return builtin + custom


@router.post("/upload")
async def upload_indicator(
    file: UploadFile = File(...),
    name: str = Form(None),
    user: str = Depends(get_current_user),
):
    """Upload an .mq5 file for AI processing. Returns job_id."""
    if not file.filename or not file.filename.endswith(".mq5"):
        raise HTTPException(status_code=400, detail="Only .mq5 files are accepted")

    processor = app_state.get("indicator_processor")
    if not processor:
        raise HTTPException(status_code=503, detail="Indicator processor not available")

    content = await file.read()
    mq5_source = content.decode("utf-8", errors="replace")

    if len(mq5_source.strip()) < 50:
        raise HTTPException(status_code=400, detail="File too small to be a valid MQL5 indicator")

    # Default name from filename
    indicator_name = name or file.filename.replace(".mq5", "")

    job_id = processor.start_processing(mq5_source, indicator_name)

    return {"job_id": job_id, "status": "pending", "indicator_name": indicator_name}


@router.get("/jobs/{job_id}")
async def get_job_status(job_id: str, user: str = Depends(get_current_user)):
    """Poll processing job status."""
    processor = app_state.get("indicator_processor")
    if not processor:
        raise HTTPException(status_code=503, detail="Indicator processor not available")

    job = processor.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return job


@router.get("/{name}")
async def get_indicator_detail(name: str, user: str = Depends(get_current_user)):
    """Get full detail for an indicator including skill content."""
    # Check built-in
    for entry in _load_builtin_catalog():
        if entry["name"] == name:
            skill_path = Path(__file__).parent.parent / "indicators" / "skills" / f"{name}.md"
            skill_content = skill_path.read_text(encoding="utf-8") if skill_path.exists() else None
            return {**entry, "source": "builtin", "skill": skill_content}

    # Check custom
    ind_dir = get_custom_indicator_dir(name)
    if not ind_dir:
        raise HTTPException(status_code=404, detail=f"Indicator '{name}' not found")

    catalog_path = ind_dir / "catalog_entry.json"
    entry = json.loads(catalog_path.read_text(encoding="utf-8")) if catalog_path.exists() else {"name": name}

    skill_path = ind_dir / "skill.md"
    skill_content = skill_path.read_text(encoding="utf-8") if skill_path.exists() else None

    meta_path = ind_dir / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else None

    return {**entry, "source": "custom", "skill": skill_content, "meta": meta}


@router.get("/{name}/code")
async def get_indicator_code(name: str, user: str = Depends(get_current_user)):
    """View generated Python + MQL5 source for a custom indicator."""
    ind_dir = get_custom_indicator_dir(name)
    if not ind_dir:
        raise HTTPException(status_code=404, detail=f"Custom indicator '{name}' not found")

    compute_path = ind_dir / "compute.py"
    source_path = ind_dir / "source.mq5"

    return {
        "name": name,
        "compute_py": compute_path.read_text(encoding="utf-8") if compute_path.exists() else None,
        "source_mq5": source_path.read_text(encoding="utf-8") if source_path.exists() else None,
    }


class UpdateCodeRequest(BaseModel):
    compute_py: str


@router.put("/{name}/code")
async def update_indicator_code(name: str, req: UpdateCodeRequest, user: str = Depends(get_current_user)):
    """Edit generated Python code for a custom indicator."""
    ind_dir = get_custom_indicator_dir(name)
    if not ind_dir:
        raise HTTPException(status_code=404, detail=f"Custom indicator '{name}' not found")

    # Validate syntax
    try:
        compile(req.compute_py, "<compute_py>", "exec")
    except SyntaxError as e:
        raise HTTPException(status_code=400, detail=f"Python syntax error: {e}")

    compute_path = ind_dir / "compute.py"
    compute_path.write_text(req.compute_py, encoding="utf-8")

    return {"status": "updated", "name": name}


@router.delete("/{name}")
async def remove_indicator(name: str, user: str = Depends(get_current_user)):
    """Delete a custom indicator."""
    deleted = delete_custom_indicator(name)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Custom indicator '{name}' not found")

    return {"status": "deleted", "name": name}
