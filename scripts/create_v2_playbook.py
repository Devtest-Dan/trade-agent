"""Create improved SMC Trend v2 playbook and load into DB."""
import json
import asyncio
from pathlib import Path
from agent.db.database import Database
from agent.models.playbook import PlaybookConfig

improved = {
    "$schema": "playbook-v1",
    "id": "smc-trend-v2",
    "name": "SMC Trend v2 (Improved)",
    "description": "Improved: wider SL (2.5 ATR), ADX>20 filter, NWE confirmation, Kernel AO momentum, partial close at TP1, trail after 2.5R",
    "symbols": ["XAUUSD", "EURUSD", "GBPJPY"],
    "autonomy": "signal_only",
    "indicators": [
        {"id": "h4_smc", "name": "SMC_Structure", "timeframe": "H4", "params": {"swing_length": 5}},
        {"id": "h1_rsi", "name": "RSI", "timeframe": "H1", "params": {"period": 14}},
        {"id": "h1_atr", "name": "ATR", "timeframe": "H1", "params": {"period": 14}},
        {"id": "h4_adx", "name": "ADX", "timeframe": "H4", "params": {"period": 14}},
        {"id": "h1_nwe", "name": "NW_Envelope", "timeframe": "H1", "params": {"h": 8, "alpha": 8, "x_0": 25}},
        {"id": "h1_kernel_ao", "name": "Kernel_AO", "timeframe": "H1", "params": {}},
    ],
    "variables": {
        "entry_price": {"type": "float", "default": 0.0},
        "initial_sl": {"type": "float", "default": 0.0},
        "tp1": {"type": "float", "default": 0.0},
        "tp2": {"type": "float", "default": 0.0},
    },
    "initial_phase": "scanning",
    "phases": {
        "scanning": {
            "description": "Wait for H4 trend + ADX trending + H1 RSI extreme + NWE + Kernel AO confirmation",
            "evaluate_on": ["H1"],
            "transitions": [
                {
                    "to": "in_long",
                    "priority": 2,
                    "conditions": {
                        "type": "AND",
                        "rules": [
                            {"left": "ind.h4_smc.trend", "operator": "==", "right": "1", "description": "H4 bullish trend"},
                            {"left": "ind.h4_adx.adx", "operator": ">", "right": "20", "description": "ADX > 20 trending"},
                            {"left": "ind.h1_rsi.value", "operator": "<", "right": "30", "description": "H1 RSI < 30 oversold"},
                            {"left": "prev.h1_rsi.value", "operator": ">=", "right": "30", "description": "RSI just crossed below 30"},
                            {"left": "ind.h1_nwe.is_bullish", "operator": "==", "right": "1", "description": "NWE bullish"},
                            {"left": "ind.h1_kernel_ao.is_rising", "operator": "==", "right": "1", "description": "Kernel AO rising"},
                        ]
                    },
                    "actions": [
                        {"set_var": "entry_price", "expr": "_price"},
                        {"set_var": "initial_sl", "expr": "_price - ind.h1_atr.value * 2.5"},
                        {"set_var": "tp1", "expr": "_price + ind.h1_atr.value * 2"},
                        {"set_var": "tp2", "expr": "_price + ind.h1_atr.value * 4"},
                        {"open_trade": {
                            "direction": "BUY",
                            "sl": {"expr": "_price - ind.h1_atr.value * 2.5"},
                            "tp": {"expr": "_price + ind.h1_atr.value * 4"},
                        }},
                    ]
                },
                {
                    "to": "in_short",
                    "priority": 1,
                    "conditions": {
                        "type": "AND",
                        "rules": [
                            {"left": "ind.h4_smc.trend", "operator": "==", "right": "-1", "description": "H4 bearish trend"},
                            {"left": "ind.h4_adx.adx", "operator": ">", "right": "20", "description": "ADX > 20 trending"},
                            {"left": "ind.h1_rsi.value", "operator": ">", "right": "70", "description": "H1 RSI > 70 overbought"},
                            {"left": "prev.h1_rsi.value", "operator": "<=", "right": "70", "description": "RSI just crossed above 70"},
                            {"left": "ind.h1_nwe.is_bearish", "operator": "==", "right": "1", "description": "NWE bearish"},
                            {"left": "ind.h1_kernel_ao.is_rising", "operator": "==", "right": "0", "description": "Kernel AO falling"},
                        ]
                    },
                    "actions": [
                        {"set_var": "entry_price", "expr": "_price"},
                        {"set_var": "initial_sl", "expr": "_price + ind.h1_atr.value * 2.5"},
                        {"set_var": "tp1", "expr": "_price - ind.h1_atr.value * 2"},
                        {"set_var": "tp2", "expr": "_price - ind.h1_atr.value * 4"},
                        {"open_trade": {
                            "direction": "SELL",
                            "sl": {"expr": "_price + ind.h1_atr.value * 2.5"},
                            "tp": {"expr": "_price - ind.h1_atr.value * 4"},
                        }},
                    ]
                }
            ],
            "timeout": None,
            "position_management": [],
            "on_trade_closed": None,
        },
        "in_long": {
            "description": "Managing long position with breakeven, partial close, and trailing stop",
            "evaluate_on": ["H1"],
            "transitions": [
                {
                    "to": "scanning",
                    "priority": 1,
                    "conditions": {
                        "type": "AND",
                        "rules": [
                            {"left": "ind.h4_smc.trend", "operator": "==", "right": "-1", "description": "H4 trend flipped bearish"}
                        ]
                    },
                    "actions": [{"close_trade": True}]
                }
            ],
            "timeout": {"bars": 60, "timeframe": "H1", "to": "scanning"},
            "position_management": [
                {
                    "name": "breakeven_1_5r",
                    "once": True,
                    "when": {"type": "AND", "rules": [
                        {"left": "_price", "operator": ">=", "right": "var.entry_price + ind.h1_atr.value * 1.5", "description": "1.5R profit"}
                    ]},
                    "modify_sl": {"expr": "var.entry_price + ind.h1_atr.value * 0.3"},
                },
                {
                    "name": "partial_close_tp1",
                    "once": True,
                    "when": {"type": "AND", "rules": [
                        {"left": "_price", "operator": ">=", "right": "var.tp1", "description": "Price reached TP1"}
                    ]},
                    "partial_close": {"pct": 50},
                },
                {
                    "name": "trail_stop",
                    "once": False,
                    "when": {"type": "AND", "rules": [
                        {"left": "_price", "operator": ">=", "right": "var.entry_price + ind.h1_atr.value * 2.5", "description": "2.5R — trail"}
                    ]},
                    "trail_sl": {"distance": {"expr": "ind.h1_atr.value * 1.5"}},
                },
            ],
            "on_trade_closed": {"to": "scanning"},
        },
        "in_short": {
            "description": "Managing short position with breakeven, partial close, and trailing stop",
            "evaluate_on": ["H1"],
            "transitions": [
                {
                    "to": "scanning",
                    "priority": 1,
                    "conditions": {
                        "type": "AND",
                        "rules": [
                            {"left": "ind.h4_smc.trend", "operator": "==", "right": "1", "description": "H4 trend flipped bullish"}
                        ]
                    },
                    "actions": [{"close_trade": True}]
                }
            ],
            "timeout": {"bars": 60, "timeframe": "H1", "to": "scanning"},
            "position_management": [
                {
                    "name": "breakeven_1_5r",
                    "once": True,
                    "when": {"type": "AND", "rules": [
                        {"left": "_price", "operator": "<=", "right": "var.entry_price - ind.h1_atr.value * 1.5", "description": "1.5R profit"}
                    ]},
                    "modify_sl": {"expr": "var.entry_price - ind.h1_atr.value * 0.3"},
                },
                {
                    "name": "partial_close_tp1",
                    "once": True,
                    "when": {"type": "AND", "rules": [
                        {"left": "_price", "operator": "<=", "right": "var.tp1", "description": "Price reached TP1"}
                    ]},
                    "partial_close": {"pct": 50},
                },
                {
                    "name": "trail_stop",
                    "once": False,
                    "when": {"type": "AND", "rules": [
                        {"left": "_price", "operator": "<=", "right": "var.entry_price - ind.h1_atr.value * 2.5", "description": "2.5R — trail"}
                    ]},
                    "trail_sl": {"distance": {"expr": "ind.h1_atr.value * 1.5"}},
                },
            ],
            "on_trade_closed": {"to": "scanning"},
        }
    },
    "risk": {
        "max_lot": 0.1,
        "max_daily_trades": 10,
        "max_drawdown_pct": 5.0,
        "max_open_positions": 1,
    }
}

# Validate
config = PlaybookConfig(**improved)
print(f"Valid! Phases: {list(config.phases.keys())}")
print(f"Indicators: {[i.id for i in config.indicators]}")

# Save to file
Path("data/playbooks/smc_trend_v2.json").write_text(json.dumps(improved, indent=2))
print("Saved to data/playbooks/smc_trend_v2.json")


async def load():
    db = Database("data/trade_agent.db")
    await db.connect()
    cursor = await db._db.execute(
        "INSERT INTO playbooks (name, description_nl, config_json, autonomy, enabled, explanation) VALUES (?, ?, ?, ?, 0, ?)",
        (improved["name"], improved["description"], json.dumps(improved), "signal_only", ""),
    )
    await db._db.commit()
    print(f"Created playbook #{cursor.lastrowid}")
    await db.disconnect()


asyncio.run(load())
