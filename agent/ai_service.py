"""AI Service — Claude API (primary) with Claude Code CLI fallback."""

import asyncio
import json
import re
import shutil
import time
from pathlib import Path
from typing import Any

import anthropic
from loguru import logger

from agent.config import settings
from agent.indicators.custom import list_custom_catalog_entries, list_custom_keywords
from agent.models.strategy import StrategyConfig
from agent.models.playbook import PlaybookConfig

_PLACEHOLDER_KEYS = {"", "sk-ant-xxxxx", "your-api-key-here"}


class AIService:
    def __init__(self):
        self._api_key = settings.anthropic_api_key
        self._client: anthropic.Anthropic | None = None

        # Try to initialize Anthropic API client
        if self._api_key and self._api_key not in _PLACEHOLDER_KEYS:
            try:
                self._client = anthropic.Anthropic(api_key=self._api_key)
                logger.info("AI Service: Using Anthropic API (key configured)")
            except Exception as e:
                logger.warning(f"AI Service: Failed to init Anthropic client: {e}")
                self._client = None

        if not self._client:
            cli_path = shutil.which("claude")
            if cli_path:
                logger.info(f"AI Service: No valid API key — using Claude Code CLI fallback ({cli_path})")
            else:
                logger.warning("AI Service: No API key AND Claude Code CLI not found — AI features disabled")

        # Load prompts and catalog
        self._indicator_catalog = self._load_catalog()
        self._parser_prompt = self._load_prompt("strategy_parser.md")
        self._reasoner_prompt = self._load_prompt("signal_reasoner.md")
        self._chat_prompt = self._load_prompt("strategy_chat.md")
        self._playbook_builder_prompt = self._load_prompt("playbook_builder.md")
        self._playbook_refiner_prompt = self._load_prompt("playbook_refiner.md")
        self._skills_dir = Path(__file__).parent / "indicators" / "skills"

    # ── Properties ──────────────────────────────────────────────────

    @property
    def provider(self) -> str:
        """Current AI provider: 'api', 'cli', or 'none'."""
        if self._client:
            return "api"
        if shutil.which("claude"):
            return "cli"
        return "none"

    @property
    def api_key_set(self) -> bool:
        return bool(self._api_key and self._api_key not in _PLACEHOLDER_KEYS)

    def update_api_key(self, key: str):
        """Update the API key at runtime and reinitialize the client."""
        self._api_key = key
        if key and key not in _PLACEHOLDER_KEYS:
            try:
                self._client = anthropic.Anthropic(api_key=key)
                logger.info("AI Service: Switched to Anthropic API (key updated)")
            except Exception as e:
                logger.warning(f"AI Service: Failed to init client with new key: {e}")
                self._client = None
        else:
            self._client = None
            logger.info("AI Service: Cleared API key — using Claude Code CLI fallback")

    # ── Unified call dispatcher ─────────────────────────────────────

    async def _call(
        self,
        system: str,
        messages: list[dict],
        model: str = "sonnet",
        max_tokens: int = 4096,
    ) -> tuple[str, dict]:
        """Route to API or CLI. Returns (response_text, usage_dict)."""
        if self._client:
            return self._call_api(system, messages, model, max_tokens)
        return await self._call_cli(system, messages, max_tokens)

    def _call_api(
        self,
        system: str,
        messages: list[dict],
        model: str,
        max_tokens: int,
    ) -> tuple[str, dict]:
        """Direct Anthropic API call."""
        model_id = {
            "opus": "claude-opus-4-20250514",
            "sonnet": "claude-sonnet-4-20250514",
            "haiku": "claude-haiku-4-5-20251001",
        }.get(model, model)

        response = self._client.messages.create(
            model=model_id,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
        )

        text = response.content[0].text
        usage = {
            "model": model_id,
            "prompt_tokens": response.usage.input_tokens,
            "completion_tokens": response.usage.output_tokens,
        }
        return text, usage

    async def _call_cli(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int,
    ) -> tuple[str, dict]:
        """Fallback: call Claude via Claude Code CLI (uses user's subscription)."""
        import os

        claude_path = shutil.which("claude")
        if not claude_path:
            raise Exception(
                "AI unavailable: No Anthropic API key configured and Claude Code CLI "
                "not found. Set your API key in Settings or install Claude Code CLI."
            )

        # Build a single prompt combining system + messages
        parts = []
        if system:
            parts.append(f"<system_instructions>\n{system}\n</system_instructions>\n")

        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            if role == "user":
                parts.append(content)
            elif role == "assistant":
                parts.append(f"[Previous assistant response]:\n{content}")

        full_prompt = "\n\n".join(parts)

        logger.info(f"AI Service [CLI]: Sending prompt ({len(full_prompt)} chars)...")

        # Clean env: unset CLAUDECODE to allow nested invocation
        env = os.environ.copy()
        env.pop("CLAUDECODE", None)

        try:
            proc = await asyncio.create_subprocess_exec(
                claude_path, "-p",
                "--output-format", "text",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=full_prompt.encode("utf-8")),
                timeout=300,  # 5 minute timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            raise Exception("Claude CLI call timed out (5 min). Try again or set an API key for faster responses.")

        if proc.returncode != 0:
            error = stderr.decode().strip()
            raise Exception(f"Claude CLI failed (exit {proc.returncode}): {error}")

        text = stdout.decode().strip()
        if not text:
            raise Exception("Claude CLI returned empty response")

        logger.info(f"AI Service [CLI]: Got response ({len(text)} chars)")

        usage = {"model": "claude-cli (subscription)", "prompt_tokens": 0, "completion_tokens": 0}
        return text, usage

    # ── Public AI methods ───────────────────────────────────────────

    async def parse_strategy(self, natural_language: str) -> StrategyConfig:
        """Parse a natural language strategy description into structured JSON config."""
        system_prompt = self._parser_prompt or self._build_parser_prompt()

        text, _ = await self._call(
            system=system_prompt,
            messages=[{
                "role": "user",
                "content": f"Parse this trading strategy into the JSON format:\n\n{natural_language}",
            }],
            model="opus",
            max_tokens=4096,
        )

        json_str = self._extract_json(text)
        config_dict = json.loads(json_str)

        # Normalize AI output — fill missing fields the model sometimes omits
        if "id" not in config_dict:
            name = config_dict.get("name", "strategy")
            config_dict["id"] = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        if "description" not in config_dict:
            config_dict["description"] = natural_language

        # Fix indicators: AI sometimes uses "type" instead of "name"
        for ind in config_dict.get("indicators", []):
            if "name" not in ind and "type" in ind:
                ind["name"] = ind.pop("type")

        return StrategyConfig(**config_dict)

    async def explain_signal(
        self,
        strategy_name: str,
        symbol: str,
        direction: str,
        conditions_snapshot: dict[str, Any],
        strategy_description: str = "",
    ) -> str:
        """Generate human-readable explanation of why a signal was triggered."""
        system_prompt = self._reasoner_prompt or (
            "You are a trading signal analyst. Explain why this trading signal was generated "
            "based on the indicator values and strategy conditions. Be concise and specific, "
            "referencing actual values."
        )

        snapshot_text = json.dumps(conditions_snapshot, indent=2)

        text, _ = await self._call(
            system=system_prompt,
            messages=[{
                "role": "user",
                "content": (
                    f"Strategy: {strategy_name}\n"
                    f"Description: {strategy_description}\n"
                    f"Symbol: {symbol}\n"
                    f"Signal: {direction}\n"
                    f"Indicator Snapshot:\n{snapshot_text}\n\n"
                    "Explain this signal in 2-3 sentences."
                ),
            }],
            model="sonnet",
            max_tokens=500,
        )

        return text

    async def chat_strategy(
        self,
        config: dict[str, Any],
        messages: list[dict[str, str]],
    ) -> str:
        """Multi-turn chat about a strategy. Returns AI response text."""
        catalog_text = json.dumps(self._indicator_catalog, indent=2)
        config_text = json.dumps(config, indent=2)

        system_prompt = (
            (self._chat_prompt or "You are a trading strategy advisor.")
            + f"\n\n## Current Strategy Config\n```json\n{config_text}\n```"
            + f"\n\n## Available Indicators\n```json\n{catalog_text}\n```"
        )

        text, _ = await self._call(
            system=system_prompt,
            messages=messages,
            model="sonnet",
            max_tokens=2048,
        )

        return text

    async def build_playbook(self, natural_language: str) -> dict:
        """Build a playbook from natural language using indicator skills files.

        Returns: {"config": PlaybookConfig, "skills_used": [...], "usage": {...}}
        """
        start = time.time()

        # Identify which indicators are mentioned
        indicator_names = self._identify_indicators(natural_language)
        logger.info(f"Identified indicators: {indicator_names}")

        # Load relevant skills files
        skills_content = self._load_skills(indicator_names)
        skills_used = list(indicator_names)

        # Build system prompt
        catalog_text = json.dumps(self._indicator_catalog, indent=2)
        system_prompt = self._playbook_builder_prompt or "You are a trading playbook builder."
        system_prompt += f"\n\n## Indicator Catalog\n```json\n{catalog_text}\n```"

        if skills_content:
            system_prompt += f"\n\n## Indicator Skills Reference\n{skills_content}"

        text, usage = await self._call(
            system=system_prompt,
            messages=[{
                "role": "user",
                "content": f"Build a playbook for this trading strategy:\n\n{natural_language}",
            }],
            model="opus",
            max_tokens=8192,
        )

        json_str = self._extract_json(text)
        config_dict = json.loads(json_str)
        config = PlaybookConfig(**config_dict)

        duration_ms = int((time.time() - start) * 1000)
        usage["duration_ms"] = duration_ms

        return {
            "config": config,
            "skills_used": skills_used,
            "usage": usage,
        }

    async def refine_playbook(
        self,
        config: dict[str, Any],
        journal_analytics: dict[str, Any],
        condition_analytics: list[dict],
        trade_samples: list[dict],
        messages: list[dict[str, str]],
    ) -> dict:
        """Refine a playbook using journal data and user conversation.

        Returns: {"reply": str, "updated_config": PlaybookConfig | None}
        """
        config_text = json.dumps(config, indent=2)
        analytics_text = json.dumps(journal_analytics, indent=2)
        conditions_text = json.dumps(condition_analytics, indent=2)
        samples_text = json.dumps(trade_samples[:10], indent=2, default=str)  # limit samples

        # Load skills for indicators in the playbook
        indicator_names = set()
        for ind in config.get("indicators", []):
            indicator_names.add(ind.get("name", ""))
        skills_content = self._load_skills(indicator_names)

        system_prompt = self._playbook_refiner_prompt or "You are a trading strategy optimizer."
        system_prompt += f"\n\n## Current Playbook\n```json\n{config_text}\n```"
        system_prompt += f"\n\n## Journal Analytics\n```json\n{analytics_text}\n```"
        system_prompt += f"\n\n## Per-Condition Win Rates\n```json\n{conditions_text}\n```"
        system_prompt += f"\n\n## Recent Trade Samples\n```json\n{samples_text}\n```"

        if skills_content:
            system_prompt += f"\n\n## Indicator Skills Reference\n{skills_content}"

        text, _ = await self._call(
            system=system_prompt,
            messages=messages,
            model="sonnet",
            max_tokens=4096,
        )

        # Check for playbook update in response
        updated_config = None
        update_match = re.search(
            r"<playbook_update>\s*(.*?)\s*</playbook_update>",
            text,
            re.DOTALL,
        )
        if update_match:
            try:
                update_json = self._extract_json(update_match.group(1))
                updated_config = PlaybookConfig(**json.loads(update_json))
            except Exception as e:
                logger.warning(f"Failed to parse playbook update: {e}")

        return {
            "reply": text,
            "updated_config": updated_config,
        }

    # ── Helpers ──────────────────────────────────────────────────────

    def _load_catalog(self) -> list[dict]:
        catalog_path = Path(__file__).parent / "indicators" / "catalog.json"
        entries = []
        if catalog_path.exists():
            entries = json.loads(catalog_path.read_text())
        # Append custom indicator catalog entries
        entries.extend(list_custom_catalog_entries())
        return entries

    def _load_prompt(self, filename: str) -> str:
        prompt_path = Path(__file__).parent / "prompts" / filename
        if prompt_path.exists():
            return prompt_path.read_text()
        return ""

    def _build_parser_prompt(self) -> str:
        """Build the strategy parser system prompt with indicator catalog."""
        catalog_text = json.dumps(self._indicator_catalog, indent=2)

        return f"""You are a trading strategy parser. Convert natural language trading strategies into structured JSON.

## Available Indicators
{catalog_text}

## Output JSON Schema
Return ONLY valid JSON matching this structure:
{{
  "id": "short-kebab-case-id",
  "name": "Human readable strategy name",
  "description": "The original natural language description",
  "version": 1,
  "symbols": ["XAUUSD"],
  "autonomy": "signal_only",
  "risk": {{
    "max_lot": 0.1,
    "max_daily_trades": 5,
    "max_drawdown_pct": 3.0,
    "max_open_positions": 2
  }},
  "timeframes_used": ["H4", "M15"],
  "indicators": [
    {{"id": "h4_rsi", "name": "RSI", "timeframe": "H4", "params": {{"period": 14}}}}
  ],
  "conditions": {{
    "entry_long": {{
      "type": "AND",
      "rules": [
        {{
          "type": "filter",
          "timeframe": "H4",
          "description": "Higher TF condition that must stay true",
          "condition": {{
            "indicator": "h4_rsi",
            "field": "value",
            "operator": "<",
            "value": 30
          }}
        }},
        {{
          "type": "trigger",
          "timeframe": "M15",
          "description": "Lower TF momentary event",
          "condition": {{
            "indicator": "m15_stoch_k",
            "field": "cross_above",
            "value": 20
          }}
        }}
      ]
    }},
    "exit_long": {{"type": "OR", "rules": [...]}},
    "entry_short": {{"type": "AND", "rules": [...]}},
    "exit_short": {{"type": "OR", "rules": [...]}}
  }}
}}

## Key Concepts
- **Filters** (type: "filter"): Higher timeframe conditions that must stay true continuously. Use operator comparisons (<, >, etc.).
- **Triggers** (type: "trigger"): Lower timeframe momentary events like crossovers. Use "cross_above" or "cross_below" in the field.
- **compare_to: "price"**: Compare indicator value to current price (bid+ask)/2.
- **Indicator IDs**: Use format "{{timeframe_lower}}_{{indicator_lower}}{{param}}" e.g. "h4_rsi", "m15_ema20".
- If a condition references two indicators crossing each other, create both indicators and use cross_above/cross_below.
- Include ALL four condition groups (entry_long, exit_long, entry_short, exit_short). Leave rules as empty array [] if not specified.
- Default symbols to ["XAUUSD"] if not mentioned.
- Valid timeframes: M1, M5, M15, M30, H1, H4, D1, W1.

Return ONLY the JSON object, no markdown code fences, no explanation."""

    def _identify_indicators(self, text: str) -> set[str]:
        """Identify indicator names mentioned in natural language text."""
        text_lower = text.lower()
        found = set()

        indicator_keywords = {
            "RSI": ["rsi", "relative strength"],
            "EMA": ["ema", "exponential moving average", "exponential ma"],
            "SMA": ["sma", "simple moving average", "simple ma", "moving average"],
            "MACD": ["macd", "moving average convergence"],
            "Stochastic": ["stochastic", "stoch"],
            "Bollinger": ["bollinger", "bb", "boll"],
            "ATR": ["atr", "average true range"],
            "ADX": ["adx", "average directional", "directional index"],
            "CCI": ["cci", "commodity channel"],
            "WilliamsR": ["williams", "williams %r", "williams r", "will%r"],
            "SMC_Structure": ["smc", "smart money", "market structure", "bos", "choch", "break of structure", "change of character", "ote", "optimal trade entry"],
            "OB_FVG": ["order block", "fair value gap", "ob", "fvg", "supply zone", "demand zone", "breaker"],
            "NW_Envelope": ["nadaraya", "nw envelope", "kernel regression", "envelope"],
        }

        for name, keywords in indicator_keywords.items():
            for kw in keywords:
                if kw in text_lower:
                    found.add(name)
                    break

        # Also check custom indicator keywords
        for name, keywords in list_custom_keywords().items():
            for kw in keywords:
                if kw.lower() in text_lower:
                    found.add(name)
                    break

        # Always include ATR for SL/TP sizing
        if found and "ATR" not in found:
            found.add("ATR")

        return found

    def _load_skills(self, indicator_names: set[str]) -> str:
        """Load skills files for the given indicator names."""
        content_parts = []

        # Always load combinations guide
        combos_path = self._skills_dir / "_combinations.md"
        if combos_path.exists():
            content_parts.append(
                f"### Indicator Combinations Guide\n{combos_path.read_text()}"
            )

        for name in sorted(indicator_names):
            skill_path = self._skills_dir / f"{name}.md"
            if skill_path.exists():
                content_parts.append(
                    f"### {name} Skills\n{skill_path.read_text()}"
                )
            else:
                # Check custom indicator skills
                from agent.indicators.custom import get_custom_indicator_dir
                custom_dir = get_custom_indicator_dir(name)
                if custom_dir:
                    custom_skill = custom_dir / "skill.md"
                    if custom_skill.exists():
                        content_parts.append(
                            f"### {name} Skills\n{custom_skill.read_text()}"
                        )
                    else:
                        logger.debug(f"No skills file for custom indicator: {name}")
                else:
                    logger.debug(f"No skills file for indicator: {name}")

        return "\n\n---\n\n".join(content_parts)

    def _extract_json(self, text: str) -> str:
        """Extract JSON from Claude's response, handling code fences."""
        text = text.strip()

        # Remove markdown code fences if present
        if text.startswith("```"):
            lines = text.split("\n")
            start = 1
            end = len(lines) - 1
            if lines[0].startswith("```json"):
                start = 1
            if lines[-1].strip() == "```":
                end = -1
            text = "\n".join(lines[start:end]).strip()

        # Find first { and last }
        first_brace = text.find("{")
        last_brace = text.rfind("}")
        if first_brace != -1 and last_brace != -1:
            text = text[first_brace : last_brace + 1]

        return text
