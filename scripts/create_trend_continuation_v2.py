"""Create reworked Trend Continuation strategy and load into DB."""
import json
import asyncio
from pathlib import Path
from agent.db.database import Database
from agent.models.playbook import PlaybookConfig

playbook = {
    "$schema": "playbook-v1",
    "id": "trend-continuation-v2",
    "name": "Trend Continuation v2",
    "description": "Trade with the H4 trend. Wait for pullback to discount/premium zone on H1, enter when RSI confirms momentum shift. ADX filter for trending markets. Wider SL, partial close, trailing stop.",
    "symbols": ["XAUUSD", "EURUSD", "GBPJPY"],
    "autonomy": "signal_only",
    "indicators": [
        {"id": "h4_smc", "name": "SMC_Structure", "timeframe": "H4", "params": {"swing_length": 5}},
        {"id": "h1_rsi", "name": "RSI", "timeframe": "H1", "params": {"period": 14}},
        {"id": "h1_atr", "name": "ATR", "timeframe": "H1", "params": {"period": 14}},
        {"id": "h4_adx", "name": "ADX", "timeframe": "H4", "params": {"period": 14}},
        {"id": "h1_bb", "name": "Bollinger", "timeframe": "H1", "params": {"period": 20, "deviation": 2.0}},
        {"id": "h1_macd", "name": "MACD", "timeframe": "H1", "params": {"fast_ema": 12, "slow_ema": 26, "signal": 9}},
    ],
    "variables": {
        "direction": {"type": "string", "default": ""},
        "setup_bar": {"type": "int", "default": 0},
        "entry_price": {"type": "float", "default": 0.0},
        "initial_sl": {"type": "float", "default": 0.0},
        "tp1": {"type": "float", "default": 0.0},
        "tp2": {"type": "float", "default": 0.0},
        "equilibrium": {"type": "float", "default": 0.0},
    },
    "initial_phase": "wait_trend",
    "phases": {
        # Phase 1: Wait for a clear H4 trend + ADX confirmation
        "wait_trend": {
            "description": "Wait for H4 trend direction with ADX showing trending market",
            "evaluate_on": ["H1"],
            "transitions": [
                {
                    "to": "wait_pullback_long",
                    "priority": 2,
                    "conditions": {
                        "type": "AND",
                        "rules": [
                            {"left": "ind.h4_smc.trend", "operator": "==", "right": "1", "description": "H4 bullish"},
                            {"left": "ind.h4_adx.adx", "operator": ">", "right": "20", "description": "ADX > 20 trending"},
                            {"left": "ind.h4_smc.equilibrium", "operator": ">", "right": "0", "description": "Equilibrium level exists"},
                        ]
                    },
                    "actions": [
                        {"set_var": "direction", "expr": "\"BUY\""},
                        {"set_var": "equilibrium", "expr": "ind.h4_smc.equilibrium"},
                    ]
                },
                {
                    "to": "wait_pullback_short",
                    "priority": 1,
                    "conditions": {
                        "type": "AND",
                        "rules": [
                            {"left": "ind.h4_smc.trend", "operator": "==", "right": "-1", "description": "H4 bearish"},
                            {"left": "ind.h4_adx.adx", "operator": ">", "right": "20", "description": "ADX > 20 trending"},
                            {"left": "ind.h4_smc.equilibrium", "operator": ">", "right": "0", "description": "Equilibrium level exists"},
                        ]
                    },
                    "actions": [
                        {"set_var": "direction", "expr": "\"SELL\""},
                        {"set_var": "equilibrium", "expr": "ind.h4_smc.equilibrium"},
                    ]
                },
            ],
            "timeout": None,
            "position_management": [],
            "on_trade_closed": None,
        },

        # Phase 2a: Wait for long pullback into discount zone
        "wait_pullback_long": {
            "description": "Price must pull back below equilibrium (discount zone) — then wait for RSI bounce",
            "evaluate_on": ["H1"],
            "transitions": [
                {
                    "to": "in_long",
                    "priority": 2,
                    "conditions": {
                        "type": "AND",
                        "rules": [
                            # Price is in discount (below equilibrium)
                            {"left": "_price", "operator": "<", "right": "var.equilibrium", "description": "Price below equilibrium (discount)"},
                            # RSI bouncing from oversold — momentum shifting up
                            {"left": "ind.h1_rsi.value", "operator": ">", "right": "35", "description": "RSI recovering from oversold"},
                            {"left": "prev.h1_rsi.value", "operator": "<=", "right": "35", "description": "RSI just crossed above 35"},
                            # H4 trend still bullish (hasn't flipped while waiting)
                            {"left": "ind.h4_smc.trend", "operator": "==", "right": "1", "description": "H4 still bullish"},
                            # MACD histogram turning up (momentum confirming)
                            {"left": "ind.h1_macd.macd", "operator": ">", "right": "ind.h1_macd.signal", "description": "MACD above signal"},
                        ]
                    },
                    "actions": [
                        {"set_var": "entry_price", "expr": "_price"},
                        {"set_var": "initial_sl", "expr": "_price - ind.h1_atr.value * 2.5"},
                        {"set_var": "tp1", "expr": "var.equilibrium"},
                        {"set_var": "tp2", "expr": "_price + ind.h1_atr.value * 4"},
                        {"open_trade": {
                            "direction": "BUY",
                            "sl": {"expr": "_price - ind.h1_atr.value * 2.5"},
                            "tp": {"expr": "_price + ind.h1_atr.value * 4"},
                        }},
                    ]
                },
                # Abort if trend flips while waiting
                {
                    "to": "wait_trend",
                    "priority": 1,
                    "conditions": {
                        "type": "AND",
                        "rules": [
                            {"left": "ind.h4_smc.trend", "operator": "!=", "right": "1", "description": "H4 trend no longer bullish"},
                        ]
                    },
                    "actions": []
                },
            ],
            "timeout": {"bars": 30, "timeframe": "H1", "to": "wait_trend"},
            "position_management": [],
            "on_trade_closed": None,
        },

        # Phase 2b: Wait for short pullback into premium zone
        "wait_pullback_short": {
            "description": "Price must pull back above equilibrium (premium zone) — then wait for RSI rejection",
            "evaluate_on": ["H1"],
            "transitions": [
                {
                    "to": "in_short",
                    "priority": 2,
                    "conditions": {
                        "type": "AND",
                        "rules": [
                            # Price is in premium (above equilibrium)
                            {"left": "_price", "operator": ">", "right": "var.equilibrium", "description": "Price above equilibrium (premium)"},
                            # RSI dropping from overbought — momentum shifting down
                            {"left": "ind.h1_rsi.value", "operator": "<", "right": "65", "description": "RSI dropping from overbought"},
                            {"left": "prev.h1_rsi.value", "operator": ">=", "right": "65", "description": "RSI just crossed below 65"},
                            # H4 trend still bearish
                            {"left": "ind.h4_smc.trend", "operator": "==", "right": "-1", "description": "H4 still bearish"},
                            # MACD histogram turning down
                            {"left": "ind.h1_macd.macd", "operator": "<", "right": "ind.h1_macd.signal", "description": "MACD below signal"},
                        ]
                    },
                    "actions": [
                        {"set_var": "entry_price", "expr": "_price"},
                        {"set_var": "initial_sl", "expr": "_price + ind.h1_atr.value * 2.5"},
                        {"set_var": "tp1", "expr": "var.equilibrium"},
                        {"set_var": "tp2", "expr": "_price - ind.h1_atr.value * 4"},
                        {"open_trade": {
                            "direction": "SELL",
                            "sl": {"expr": "_price + ind.h1_atr.value * 2.5"},
                            "tp": {"expr": "_price - ind.h1_atr.value * 4"},
                        }},
                    ]
                },
                # Abort if trend flips
                {
                    "to": "wait_trend",
                    "priority": 1,
                    "conditions": {
                        "type": "AND",
                        "rules": [
                            {"left": "ind.h4_smc.trend", "operator": "!=", "right": "-1", "description": "H4 trend no longer bearish"},
                        ]
                    },
                    "actions": []
                },
            ],
            "timeout": {"bars": 30, "timeframe": "H1", "to": "wait_trend"},
            "position_management": [],
            "on_trade_closed": None,
        },

        # Phase 3a: In long position
        "in_long": {
            "description": "Managing long — breakeven, partial close at equilibrium, trail, trend exit",
            "evaluate_on": ["H1"],
            "transitions": [
                {
                    "to": "wait_trend",
                    "priority": 1,
                    "conditions": {
                        "type": "AND",
                        "rules": [
                            {"left": "ind.h4_smc.trend", "operator": "==", "right": "-1", "description": "H4 flipped bearish — exit"}
                        ]
                    },
                    "actions": [{"close_trade": True}]
                }
            ],
            "timeout": {"bars": 80, "timeframe": "H1", "to": "wait_trend"},
            "position_management": [
                {
                    "name": "breakeven",
                    "once": True,
                    "when": {"type": "AND", "rules": [
                        {"left": "_price", "operator": ">=", "right": "var.entry_price + ind.h1_atr.value * 1.5", "description": "1.5R profit"}
                    ]},
                    "modify_sl": {"expr": "var.entry_price + ind.h1_atr.value * 0.3"},
                },
                {
                    "name": "partial_at_equilibrium",
                    "once": True,
                    "when": {"type": "AND", "rules": [
                        {"left": "_price", "operator": ">=", "right": "var.tp1", "description": "Reached equilibrium (TP1)"}
                    ]},
                    "partial_close": {"pct": 50},
                },
                {
                    "name": "trail",
                    "once": False,
                    "when": {"type": "AND", "rules": [
                        {"left": "_price", "operator": ">=", "right": "var.entry_price + ind.h1_atr.value * 2.5", "description": "2.5R — trail"}
                    ]},
                    "trail_sl": {"distance": {"expr": "ind.h1_atr.value * 1.5"}},
                },
            ],
            "on_trade_closed": {"to": "wait_trend"},
        },

        # Phase 3b: In short position
        "in_short": {
            "description": "Managing short — breakeven, partial close at equilibrium, trail, trend exit",
            "evaluate_on": ["H1"],
            "transitions": [
                {
                    "to": "wait_trend",
                    "priority": 1,
                    "conditions": {
                        "type": "AND",
                        "rules": [
                            {"left": "ind.h4_smc.trend", "operator": "==", "right": "1", "description": "H4 flipped bullish — exit"}
                        ]
                    },
                    "actions": [{"close_trade": True}]
                }
            ],
            "timeout": {"bars": 80, "timeframe": "H1", "to": "wait_trend"},
            "position_management": [
                {
                    "name": "breakeven",
                    "once": True,
                    "when": {"type": "AND", "rules": [
                        {"left": "_price", "operator": "<=", "right": "var.entry_price - ind.h1_atr.value * 1.5", "description": "1.5R profit"}
                    ]},
                    "modify_sl": {"expr": "var.entry_price - ind.h1_atr.value * 0.3"},
                },
                {
                    "name": "partial_at_equilibrium",
                    "once": True,
                    "when": {"type": "AND", "rules": [
                        {"left": "_price", "operator": "<=", "right": "var.tp1", "description": "Reached equilibrium (TP1)"}
                    ]},
                    "partial_close": {"pct": 50},
                },
                {
                    "name": "trail",
                    "once": False,
                    "when": {"type": "AND", "rules": [
                        {"left": "_price", "operator": "<=", "right": "var.entry_price - ind.h1_atr.value * 2.5", "description": "2.5R — trail"}
                    ]},
                    "trail_sl": {"distance": {"expr": "ind.h1_atr.value * 1.5"}},
                },
            ],
            "on_trade_closed": {"to": "wait_trend"},
        },
    },
    "risk": {
        "max_lot": 0.1,
        "max_daily_trades": 8,
        "max_drawdown_pct": 5.0,
        "max_open_positions": 1,
    }
}

# Validate
config = PlaybookConfig(**playbook)
print(f"Valid! Phases: {list(config.phases.keys())}")
print(f"Indicators: {[i.id for i in config.indicators]}")

# Save to file
Path("data/playbooks/trend_continuation_v2.json").write_text(json.dumps(playbook, indent=2))
print("Saved to data/playbooks/trend_continuation_v2.json")


async def load():
    db = Database("data/trade_agent.db")
    await db.connect()

    # Check if already exists
    rows = await db._db.execute_fetchall(
        "SELECT id FROM playbooks WHERE name = ?", (playbook["name"],)
    )
    if rows:
        pb_id = rows[0]["id"]
        await db._db.execute(
            "UPDATE playbooks SET config_json = ?, description_nl = ? WHERE id = ?",
            (json.dumps(playbook), playbook["description"], pb_id),
        )
        print(f"Updated playbook #{pb_id}")
    else:
        cursor = await db._db.execute(
            "INSERT INTO playbooks (name, description_nl, config_json, autonomy, enabled, explanation) VALUES (?, ?, ?, ?, 0, ?)",
            (playbook["name"], playbook["description"], json.dumps(playbook), "signal_only", ""),
        )
        print(f"Created playbook #{cursor.lastrowid}")

    await db._db.commit()
    await db.disconnect()


asyncio.run(load())
