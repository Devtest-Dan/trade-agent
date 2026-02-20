"""AI Service — Claude API for strategy parsing and signal reasoning."""

import json
from pathlib import Path
from typing import Any

import anthropic
from loguru import logger

from agent.config import settings
from agent.models.strategy import StrategyConfig


class AIService:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self._indicator_catalog = self._load_catalog()
        self._parser_prompt = self._load_prompt("strategy_parser.md")
        self._reasoner_prompt = self._load_prompt("signal_reasoner.md")
        self._chat_prompt = self._load_prompt("strategy_chat.md")

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
