"""Custom indicator plugin loader.

Discovers and loads user-uploaded indicators from custom/{Name}/ directories.
Each plugin directory must contain a compute.py that exports:
  NAME: str, KEYWORDS: list[str], EMPTY_RESULT: dict, compute(df, params) -> dict[str, float]
"""

import importlib.util
import json
import shutil
import types
from pathlib import Path
from typing import Any

from loguru import logger

CUSTOM_DIR = Path(__file__).parent

# Required exports from compute.py
_REQUIRED_EXPORTS = ("NAME", "KEYWORDS", "EMPTY_RESULT", "compute")


def _load_module(name: str, path: Path) -> types.ModuleType | None:
    """Import a compute.py file as a module, validating its interface."""
    try:
        spec = importlib.util.spec_from_file_location(f"custom_indicator_{name}", path)
        if not spec or not spec.loader:
            return None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]

        # Validate interface
        for attr in _REQUIRED_EXPORTS:
            if not hasattr(mod, attr):
                logger.warning(f"Custom indicator {name}: compute.py missing '{attr}'")
                return None

        if not callable(mod.compute):
            logger.warning(f"Custom indicator {name}: compute is not callable")
            return None

        return mod
    except Exception as e:
        logger.error(f"Failed to load custom indicator {name}: {e}")
        return None


def discover_custom_indicators() -> dict[str, types.ModuleType]:
    """Scan custom dirs, import compute.py modules, return {name: module} map."""
    modules: dict[str, types.ModuleType] = {}

    if not CUSTOM_DIR.exists():
        return modules

    for child in sorted(CUSTOM_DIR.iterdir()):
        if not child.is_dir() or child.name.startswith("_"):
            continue
        compute_path = child / "compute.py"
        if not compute_path.exists():
            continue
        mod = _load_module(child.name, compute_path)
        if mod:
            modules[mod.NAME] = mod
            logger.info(f"Loaded custom indicator: {mod.NAME}")

    return modules


def list_custom_catalog_entries() -> list[dict]:
    """Read all catalog_entry.json files from custom indicator dirs."""
    entries: list[dict] = []

    if not CUSTOM_DIR.exists():
        return entries

    for child in sorted(CUSTOM_DIR.iterdir()):
        if not child.is_dir() or child.name.startswith("_"):
            continue
        catalog_path = child / "catalog_entry.json"
        if catalog_path.exists():
            try:
                entry = json.loads(catalog_path.read_text(encoding="utf-8"))
                entry["custom"] = True
                entries.append(entry)
            except Exception as e:
                logger.warning(f"Failed to read catalog for {child.name}: {e}")

    return entries


def list_custom_keywords() -> dict[str, list[str]]:
    """Aggregate keywords from all custom indicators. Returns {name: [keywords]}."""
    keywords: dict[str, list[str]] = {}

    if not CUSTOM_DIR.exists():
        return keywords

    for child in sorted(CUSTOM_DIR.iterdir()):
        if not child.is_dir() or child.name.startswith("_"):
            continue
        compute_path = child / "compute.py"
        if not compute_path.exists():
            continue
        mod = _load_module(child.name, compute_path)
        if mod:
            keywords[mod.NAME] = list(mod.KEYWORDS)

    return keywords


def delete_custom_indicator(name: str) -> bool:
    """Remove a custom indicator directory. Returns True if deleted."""
    for child in CUSTOM_DIR.iterdir():
        if not child.is_dir() or child.name.startswith("_"):
            continue
        # Match by dir name or by module NAME
        compute_path = child / "compute.py"
        if child.name == name:
            shutil.rmtree(child)
            logger.info(f"Deleted custom indicator: {name}")
            return True
        if compute_path.exists():
            mod = _load_module(child.name, compute_path)
            if mod and mod.NAME == name:
                shutil.rmtree(child)
                logger.info(f"Deleted custom indicator: {name}")
                return True

    return False


def get_custom_indicator_dir(name: str) -> Path | None:
    """Get the directory path for a custom indicator by name."""
    for child in CUSTOM_DIR.iterdir():
        if not child.is_dir() or child.name.startswith("_"):
            continue
        if child.name == name:
            return child
        compute_path = child / "compute.py"
        if compute_path.exists():
            mod = _load_module(child.name, compute_path)
            if mod and mod.NAME == name:
                return child
    return None
