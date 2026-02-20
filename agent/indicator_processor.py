"""Indicator Processor — MQL5 → Python + Skill + Catalog via Claude.

Sends uploaded .mq5 source to Claude, which generates:
  - compute.py (Python indicator implementation)
  - skill.md (AI skill documentation)
  - catalog_entry.json (indicator schema)
  - keywords (for NL detection)

Response is parsed via XML-tagged sections.
"""

import asyncio
import json
import re
import time
import uuid
from pathlib import Path
from typing import Any

from loguru import logger

from agent.ai_service import AIService

CUSTOM_DIR = Path(__file__).parent / "indicators" / "custom"

# Example RSI compute.py for the prompt
_EXAMPLE_COMPUTE = '''
NAME = "RSI"
KEYWORDS = ["rsi", "relative strength"]
EMPTY_RESULT = {"value": 50.0}

def compute(df, params):
    """Compute RSI from OHLCV DataFrame. Returns dict of output_name → float."""
    import pandas_ta as ta
    period = params.get("period", 14)
    result = ta.rsi(df["close"], length=period)
    if result is None or result.empty:
        return {"value": 50.0}
    val = result.iloc[-1]
    return {"value": round(float(val), 4) if not (val != val) else 50.0}
'''.strip()

_SYSTEM_PROMPT = """You are a trading indicator engineer. Given an MQL5 indicator source file, generate a complete Python implementation plus documentation.

## Your Task
1. Analyze the MQL5 indicator code
2. Generate a Python compute module that replicates the indicator logic using pandas/numpy/pandas_ta
3. Generate a skill documentation file for AI playbook builders
4. Generate a catalog entry JSON schema
5. Generate keyword list for natural language detection

## Output Format
Return your response with these XML-tagged sections (ALL are required):

<compute_py>
# The full Python compute.py file
NAME = "IndicatorName"
KEYWORDS = ["keyword1", "keyword2"]
EMPTY_RESULT = {"output1": 0.0, "output2": 0.0}

def compute(df, params):
    \"\"\"Compute indicator from OHLCV DataFrame.

    Args:
        df: pandas DataFrame with columns: open, high, low, close, volume
        params: dict of parameter values

    Returns:
        dict of output_name → float value
    \"\"\"
    # Implementation here
    pass
</compute_py>

<skill_md>
# IndicatorName — Playbook Skills

## Overview
...

## When to Use
...

## Parameters Guide
| Parameter | Default | Effect of Lower | Effect of Higher | Recommendation |
|-----------|---------|-----------------|------------------|----------------|

## Key Patterns & Setups
...

## Combinations
...

## Position Management
...

## Pitfalls
...
</skill_md>

<catalog_entry>
{
  "name": "IndicatorName",
  "full_name": "Full Indicator Name",
  "description": "Brief description",
  "params": {
    "period": {"type": "int", "default": 14, "description": "Lookback period"}
  },
  "outputs": {
    "value": {"description": "The indicator value"}
  },
  "supports_cross": true,
  "timeframes": ["M5", "M15", "M30", "H1", "H4", "D1"]
}
</catalog_entry>

<keywords>
keyword1, keyword2, keyword3
</keywords>

## Example compute.py (RSI)
```python
{example}
```

## Rules
- The compute() function receives a pandas DataFrame with columns: open, high, low, close, volume
- It receives params as a dict (e.g. {{"period": 14}})
- It MUST return a dict[str, float] mapping output names to values
- Use pandas_ta for standard calculations where possible, numpy for custom logic
- Handle edge cases (insufficient data, NaN) by returning EMPTY_RESULT values
- NAME must be a valid Python identifier (PascalCase preferred)
- KEYWORDS should include common ways users might refer to this indicator
- Keep compute.py self-contained — only import pandas_ta, numpy, math, pandas
"""


class IndicatorProcessor:
    """Processes MQL5 files into Python indicator plugins via Claude."""

    def __init__(self, ai_service: AIService):
        self._ai = ai_service
        self._jobs: dict[str, dict[str, Any]] = {}

    @property
    def jobs(self) -> dict[str, dict]:
        return self._jobs

    def start_processing(self, mq5_source: str, indicator_name: str | None = None) -> str:
        """Start async processing of MQL5 source. Returns job_id."""
        job_id = str(uuid.uuid4())[:8]
        self._jobs[job_id] = {
            "id": job_id,
            "status": "pending",
            "indicator_name": indicator_name,
            "created_at": time.time(),
            "error": None,
            "result_name": None,
        }

        asyncio.create_task(self._process(job_id, mq5_source, indicator_name))
        return job_id

    def get_job(self, job_id: str) -> dict | None:
        return self._jobs.get(job_id)

    async def _process(self, job_id: str, mq5_source: str, name_hint: str | None):
        """Background task: send MQL5 to Claude, parse response, write plugin files."""
        self._jobs[job_id]["status"] = "processing"

        try:
            # Build prompt
            system = _SYSTEM_PROMPT.replace("{example}", _EXAMPLE_COMPUTE)
            user_msg = f"## MQL5 Source Code\n\n```mql5\n{mq5_source}\n```"
            if name_hint:
                user_msg += f"\n\nPreferred indicator name: {name_hint}"

            # Call Claude (reuses AIService's dual API/CLI path)
            text, usage = await self._ai._call(
                system=system,
                messages=[{"role": "user", "content": user_msg}],
                model="sonnet",
                max_tokens=8192,
            )

            # Parse XML-tagged sections
            compute_py = self._extract_tag(text, "compute_py")
            skill_md = self._extract_tag(text, "skill_md")
            catalog_json = self._extract_tag(text, "catalog_entry")
            keywords_raw = self._extract_tag(text, "keywords")

            if not compute_py:
                raise ValueError("Claude response missing <compute_py> section")
            if not catalog_json:
                raise ValueError("Claude response missing <catalog_entry> section")

            # Validate Python syntax
            compile(compute_py, "<compute_py>", "exec")

            # Parse catalog entry
            catalog_entry = json.loads(catalog_json)
            ind_name = catalog_entry.get("name", name_hint or "CustomIndicator")

            # Create plugin directory
            dir_name = re.sub(r'[^a-zA-Z0-9_]', '_', ind_name)
            plugin_dir = CUSTOM_DIR / dir_name
            plugin_dir.mkdir(parents=True, exist_ok=True)

            # Write all files
            (plugin_dir / "compute.py").write_text(compute_py, encoding="utf-8")
            (plugin_dir / "source.mq5").write_text(mq5_source, encoding="utf-8")

            if skill_md:
                (plugin_dir / "skill.md").write_text(skill_md, encoding="utf-8")

            catalog_entry["custom"] = True
            (plugin_dir / "catalog_entry.json").write_text(
                json.dumps(catalog_entry, indent=2), encoding="utf-8"
            )

            # Parse keywords
            keywords = []
            if keywords_raw:
                keywords = [k.strip() for k in keywords_raw.split(",") if k.strip()]

            # Write meta
            meta = {
                "name": ind_name,
                "dir_name": dir_name,
                "created_at": time.time(),
                "status": "complete",
                "model_used": usage.get("model", "unknown"),
                "keywords": keywords,
            }
            (plugin_dir / "meta.json").write_text(
                json.dumps(meta, indent=2), encoding="utf-8"
            )

            self._jobs[job_id]["status"] = "complete"
            self._jobs[job_id]["result_name"] = ind_name

            logger.info(f"Indicator processing complete: {ind_name} (job {job_id})")

        except Exception as e:
            logger.error(f"Indicator processing failed (job {job_id}): {e}")
            self._jobs[job_id]["status"] = "error"
            self._jobs[job_id]["error"] = str(e)

    @staticmethod
    def _extract_tag(text: str, tag: str) -> str | None:
        """Extract content between <tag> and </tag>."""
        pattern = rf"<{tag}>(.*?)</{tag}>"
        match = re.search(pattern, text, re.DOTALL)
        if match:
            return match.group(1).strip()
        return None
