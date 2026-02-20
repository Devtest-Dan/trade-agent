"""AI Service — Claude API for strategy parsing, playbook building, and refinement."""

import json
import re
import time
from pathlib import Path
from typing import Any

import anthropic
from loguru import logger

from agent.config import settings
from agent.models.strategy import StrategyConfig
from agent.models.playbook import PlaybookConfig


class AIService:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self._indicator_catalog = self._load_catalog()
        self._parser_prompt = self._load_prompt("strategy_parser.md")
        self._reasoner_prompt = self._load_prompt("signal_reasoner.md")
        self._chat_prompt = self._load_prompt("strategy_chat.md")
        self._playbook_builder_prompt = self._load_prompt("playbook_builder.md")
        self._playbook_refiner_prompt = self._load_prompt("playbook_refiner.md")
        self._skills_dir = Path(__file__).parent / "indicators" / "skills"

    def _load_catalog(self) -> list[dict]:
        catalog_path = Path(__file__).parent / "indicators" / "catalog.json"
        if catalog_path.exists():
            return json.loads(catalog_path.read_text())
        return []

    def _load_prompt(self, filename: str) -> str:
        prompt_path = Path(__file__).parent / "prompts" / filename
        if prompt_path.exists():
            return prompt_path.read_text()
        return ""

    async def parse_strategy(self, natural_language: str) -> StrategyConfig:
        """Parse a natural language strategy description into structured JSON config."""
        system_prompt = self._parser_prompt or self._build_parser_prompt()

        response = self.client.messages.create(
            model="claude-opus-4-20250514",
            max_tokens=4096,
            system=system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": f"Parse this trading strategy into the JSON format:\n\n{natural_language}",
                }
            ],
        )

        # Extract JSON from response
        text = response.content[0].text
        json_str = self._extract_json(text)
        config_dict = json.loads(json_str)

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

        response = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            system=system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Strategy: {strategy_name}\n"
                        f"Description: {strategy_description}\n"
                        f"Symbol: {symbol}\n"
                        f"Signal: {direction}\n"
                        f"Indicator Snapshot:\n{snapshot_text}\n\n"
                        "Explain this signal in 2-3 sentences."
                    ),
                }
            ],
        )

        return response.content[0].text

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

        response = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2048,
            system=system_prompt,
            messages=messages,
        )

        return response.content[0].text

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

        response = self.client.messages.create(
            model="claude-opus-4-20250514",
            max_tokens=8192,
            system=system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": f"Build a playbook for this trading strategy:\n\n{natural_language}",
                }
            ],
        )

        text = response.content[0].text
        json_str = self._extract_json(text)
        config_dict = json.loads(json_str)
        config = PlaybookConfig(**config_dict)

        duration_ms = int((time.time() - start) * 1000)

        return {
            "config": config,
            "skills_used": skills_used,
            "usage": {
                "model": "claude-opus-4-20250514",
                "prompt_tokens": response.usage.input_tokens,
                "completion_tokens": response.usage.output_tokens,
                "duration_ms": duration_ms,
            },
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

        response = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            system=system_prompt,
            messages=messages,
        )

        reply = response.content[0].text

        # Check for playbook update in response
        updated_config = None
        update_match = re.search(
            r"<playbook_update>\s*(.*?)\s*</playbook_update>",
            reply,
            re.DOTALL,
        )
        if update_match:
            try:
                update_json = self._extract_json(update_match.group(1))
                updated_config = PlaybookConfig(**json.loads(update_json))
            except Exception as e:
                logger.warning(f"Failed to parse playbook update: {e}")

        return {
            "reply": reply,
            "updated_config": updated_config,
        }

    def _identify_indicators(self, text: str) -> set[str]:
        """Identify indicator names mentioned in natural language text."""
        text_lower = text.lower()
        found = set()

        # Direct name matches
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

        # Always include ATR for SL/TP sizing
        if found and "ATR" not in found:
            found.add("ATR")

        # Always load combinations guide
        # (handled in _load_skills)

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
