"""Create reworked SMC Reversal and Divergence Reversal strategies."""
import json
import asyncio
from pathlib import Path
from agent.db.database import Database
from agent.models.playbook import PlaybookConfig


# ═══════════════════════════════════════════════════════════════════
# Strategy 1: SMC Reversal v2
# ═══════════════════════════════════════════════════════════════════
# Original problem: required CHoCH event flag (single-bar) — never fires
# Fix: detect trend reversal by checking if H4 trend CHANGED from previous
# evaluation. Phase 1 tracks the trend, Phase 2 waits for pullback after flip.

smc_reversal_v2 = {
    "$schema": "playbook-v1",
    "id": "smc-reversal-v2",
    "name": "SMC Reversal v2",
    "description": "Detect H4 trend reversals. When H4 trend flips, wait for H1 pullback to OTE/equilibrium zone, enter when RSI bounces with MACD confirmation.",
    "symbols": ["XAUUSD", "EURUSD", "GBPJPY"],
    "autonomy": "signal_only",
    "indicators": [
        {"id": "h4_smc", "name": "SMC_Structure", "timeframe": "H4", "params": {"swing_length": 5}},
        {"id": "h1_rsi", "name": "RSI", "timeframe": "H1", "params": {"period": 14}},
        {"id": "h1_atr", "name": "ATR", "timeframe": "H1", "params": {"period": 14}},
        {"id": "h4_adx", "name": "ADX", "timeframe": "H4", "params": {"period": 14}},
        {"id": "h1_macd", "name": "MACD", "timeframe": "H1", "params": {"fast_ema": 12, "slow_ema": 26, "signal": 9}},
        {"id": "h1_stoch", "name": "Stochastic", "timeframe": "H1", "params": {"k_period": 5, "d_period": 3, "slowing": 3}},
    ],
    "variables": {
        "prev_trend": {"type": "float", "default": 0.0},
        "trend_flipped": {"type": "bool", "default": False},
        "entry_price": {"type": "float", "default": 0.0},
        "initial_sl": {"type": "float", "default": 0.0},
        "tp1": {"type": "float", "default": 0.0},
        "tp2": {"type": "float", "default": 0.0},
        "equilibrium": {"type": "float", "default": 0.0},
        "strong_level": {"type": "float", "default": 0.0},
    },
    "initial_phase": "track_trend",
    "phases": {
        # Phase 1: Track H4 trend and detect flips
        # Every bar, save current trend to prev_trend
        # When trend differs from prev_trend, we have a reversal
        "track_trend": {
            "description": "Track H4 trend direction. Detect when it flips.",
            "evaluate_on": ["H1"],
            "transitions": [
                # Bearish -> Bullish flip: trend was -1, now is 1
                {
                    "to": "wait_pullback_long",
                    "priority": 3,
                    "conditions": {
                        "type": "AND",
                        "rules": [
                            {"left": "ind.h4_smc.trend", "operator": "==", "right": "1", "description": "H4 now bullish"},
                            {"left": "var.prev_trend", "operator": "==", "right": "-1", "description": "Was bearish before"},
                        ]
                    },
                    "actions": [
                        {"set_var": "equilibrium", "expr": "ind.h4_smc.equilibrium"},
                        {"set_var": "strong_level", "expr": "ind.h4_smc.strong_low"},
                        {"set_var": "prev_trend", "expr": "ind.h4_smc.trend"},
                    ]
                },
                # Bullish -> Bearish flip: trend was 1, now is -1
                {
                    "to": "wait_pullback_short",
                    "priority": 2,
                    "conditions": {
                        "type": "AND",
                        "rules": [
                            {"left": "ind.h4_smc.trend", "operator": "==", "right": "-1", "description": "H4 now bearish"},
                            {"left": "var.prev_trend", "operator": "==", "right": "1", "description": "Was bullish before"},
                        ]
                    },
                    "actions": [
                        {"set_var": "equilibrium", "expr": "ind.h4_smc.equilibrium"},
                        {"set_var": "strong_level", "expr": "ind.h4_smc.strong_high"},
                        {"set_var": "prev_trend", "expr": "ind.h4_smc.trend"},
                    ]
                },
                # No flip — just update prev_trend for next check
                {
                    "to": "track_trend",
                    "priority": 1,
                    "conditions": {
                        "type": "AND",
                        "rules": [
                            {"left": "ind.h4_smc.trend", "operator": "!=", "right": "0", "description": "Trend defined"},
                            {"left": "ind.h4_smc.trend", "operator": "!=", "right": "var.prev_trend", "description": "Trend changed (from undefined)"},
                        ]
                    },
                    "actions": [
                        {"set_var": "prev_trend", "expr": "ind.h4_smc.trend"},
                    ]
                },
            ],
            "timeout": None,
            "position_management": [],
            "on_trade_closed": None,
        },

        # Phase 2a: Wait for pullback after bullish reversal
        "wait_pullback_long": {
            "description": "After bullish reversal, wait for price pullback + RSI bounce from oversold",
            "evaluate_on": ["H1"],
            "transitions": [
                {
                    "to": "in_long",
                    "priority": 2,
                    "conditions": {
                        "type": "AND",
                        "rules": [
                            # Price pulled back (RSI was oversold, now bouncing)
                            {"left": "ind.h1_rsi.value", "operator": ">", "right": "35", "description": "RSI bouncing up"},
                            {"left": "prev.h1_rsi.value", "operator": "<=", "right": "35", "description": "RSI just crossed above 35"},
                            # MACD confirming momentum
                            {"left": "ind.h1_macd.macd", "operator": ">", "right": "ind.h1_macd.signal", "description": "MACD bullish"},
                            # Still in bullish trend
                            {"left": "ind.h4_smc.trend", "operator": "==", "right": "1", "description": "H4 still bullish"},
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
                # Trend flipped back — abort
                {
                    "to": "track_trend",
                    "priority": 1,
                    "conditions": {
                        "type": "AND",
                        "rules": [
                            {"left": "ind.h4_smc.trend", "operator": "!=", "right": "1", "description": "H4 no longer bullish"},
                        ]
                    },
                    "actions": [
                        {"set_var": "prev_trend", "expr": "ind.h4_smc.trend"},
                    ]
                },
            ],
            "timeout": {"bars": 40, "timeframe": "H1", "to": "track_trend"},
            "position_management": [],
            "on_trade_closed": None,
        },

        # Phase 2b: Wait for pullback after bearish reversal
        "wait_pullback_short": {
            "description": "After bearish reversal, wait for price pullback + RSI drop from overbought",
            "evaluate_on": ["H1"],
            "transitions": [
                {
                    "to": "in_short",
                    "priority": 2,
                    "conditions": {
                        "type": "AND",
                        "rules": [
                            {"left": "ind.h1_rsi.value", "operator": "<", "right": "65", "description": "RSI dropping"},
                            {"left": "prev.h1_rsi.value", "operator": ">=", "right": "65", "description": "RSI just crossed below 65"},
                            {"left": "ind.h1_macd.macd", "operator": "<", "right": "ind.h1_macd.signal", "description": "MACD bearish"},
                            {"left": "ind.h4_smc.trend", "operator": "==", "right": "-1", "description": "H4 still bearish"},
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
                {
                    "to": "track_trend",
                    "priority": 1,
                    "conditions": {
                        "type": "AND",
                        "rules": [
                            {"left": "ind.h4_smc.trend", "operator": "!=", "right": "-1", "description": "H4 no longer bearish"},
                        ]
                    },
                    "actions": [
                        {"set_var": "prev_trend", "expr": "ind.h4_smc.trend"},
                    ]
                },
            ],
            "timeout": {"bars": 40, "timeframe": "H1", "to": "track_trend"},
            "position_management": [],
            "on_trade_closed": None,
        },

        # Phase 3a: In long
        "in_long": {
            "description": "Managing long — breakeven, partial, trail, trend exit",
            "evaluate_on": ["H1"],
            "transitions": [
                {
                    "to": "track_trend",
                    "priority": 1,
                    "conditions": {
                        "type": "AND",
                        "rules": [
                            {"left": "ind.h4_smc.trend", "operator": "==", "right": "-1", "description": "Trend flipped bearish"},
                        ]
                    },
                    "actions": [
                        {"close_trade": True},
                        {"set_var": "prev_trend", "expr": "-1"},
                    ]
                }
            ],
            "timeout": {"bars": 70, "timeframe": "H1", "to": "track_trend"},
            "position_management": [
                {
                    "name": "breakeven",
                    "once": True,
                    "when": {"type": "AND", "rules": [
                        {"left": "_price", "operator": ">=", "right": "var.entry_price + ind.h1_atr.value * 1.5", "description": "1.5R"}
                    ]},
                    "modify_sl": {"expr": "var.entry_price + ind.h1_atr.value * 0.3"},
                },
                {
                    "name": "partial_tp1",
                    "once": True,
                    "when": {"type": "AND", "rules": [
                        {"left": "_price", "operator": ">=", "right": "var.entry_price + ind.h1_atr.value * 2", "description": "2R"}
                    ]},
                    "partial_close": {"pct": 50},
                },
                {
                    "name": "trail",
                    "once": False,
                    "when": {"type": "AND", "rules": [
                        {"left": "_price", "operator": ">=", "right": "var.entry_price + ind.h1_atr.value * 2.5", "description": "2.5R"}
                    ]},
                    "trail_sl": {"distance": {"expr": "ind.h1_atr.value * 1.5"}},
                },
            ],
            "on_trade_closed": {"to": "track_trend"},
        },

        # Phase 3b: In short
        "in_short": {
            "description": "Managing short — breakeven, partial, trail, trend exit",
            "evaluate_on": ["H1"],
            "transitions": [
                {
                    "to": "track_trend",
                    "priority": 1,
                    "conditions": {
                        "type": "AND",
                        "rules": [
                            {"left": "ind.h4_smc.trend", "operator": "==", "right": "1", "description": "Trend flipped bullish"},
                        ]
                    },
                    "actions": [
                        {"close_trade": True},
                        {"set_var": "prev_trend", "expr": "1"},
                    ]
                }
            ],
            "timeout": {"bars": 70, "timeframe": "H1", "to": "track_trend"},
            "position_management": [
                {
                    "name": "breakeven",
                    "once": True,
                    "when": {"type": "AND", "rules": [
                        {"left": "_price", "operator": "<=", "right": "var.entry_price - ind.h1_atr.value * 1.5", "description": "1.5R"}
                    ]},
                    "modify_sl": {"expr": "var.entry_price - ind.h1_atr.value * 0.3"},
                },
                {
                    "name": "partial_tp1",
                    "once": True,
                    "when": {"type": "AND", "rules": [
                        {"left": "_price", "operator": "<=", "right": "var.entry_price - ind.h1_atr.value * 2", "description": "2R"}
                    ]},
                    "partial_close": {"pct": 50},
                },
                {
                    "name": "trail",
                    "once": False,
                    "when": {"type": "AND", "rules": [
                        {"left": "_price", "operator": "<=", "right": "var.entry_price - ind.h1_atr.value * 2.5", "description": "2.5R"}
                    ]},
                    "trail_sl": {"distance": {"expr": "ind.h1_atr.value * 1.5"}},
                },
            ],
            "on_trade_closed": {"to": "track_trend"},
        },
    },
    "risk": {
        "max_lot": 0.1,
        "max_daily_trades": 5,
        "max_drawdown_pct": 5.0,
        "max_open_positions": 1,
    }
}


# ═══════════════════════════════════════════════════════════════════
# Strategy 2: Divergence Reversal v2
# ═══════════════════════════════════════════════════════════════════
# Original problem: required bull_reg_div event flag — single bar event
# Fix: use RSI divergence detection instead. When price makes lower low
# but RSI makes higher low (H1), that's a bullish divergence. Detect
# this by tracking RSI at swing lows via Stochastic extreme + price
# near H4 strong level.

divergence_reversal_v2 = {
    "$schema": "playbook-v1",
    "id": "divergence-reversal-v2",
    "name": "Divergence Reversal v2",
    "description": "Detect momentum exhaustion at key levels. Enter when H1 RSI is extreme + Stochastic crosses + price near H4 strong level + MACD diverging. Counter-trend entries with tight management.",
    "symbols": ["XAUUSD", "EURUSD", "GBPJPY"],
    "autonomy": "signal_only",
    "indicators": [
        {"id": "h4_smc", "name": "SMC_Structure", "timeframe": "H4", "params": {"swing_length": 5}},
        {"id": "h1_rsi", "name": "RSI", "timeframe": "H1", "params": {"period": 14}},
        {"id": "h1_atr", "name": "ATR", "timeframe": "H1", "params": {"period": 14}},
        {"id": "h1_stoch", "name": "Stochastic", "timeframe": "H1", "params": {"k_period": 14, "d_period": 3, "slowing": 3}},
        {"id": "h1_macd", "name": "MACD", "timeframe": "H1", "params": {"fast_ema": 12, "slow_ema": 26, "signal": 9}},
        {"id": "h1_bb", "name": "Bollinger", "timeframe": "H1", "params": {"period": 20, "deviation": 2.0}},
    ],
    "variables": {
        "entry_price": {"type": "float", "default": 0.0},
        "initial_sl": {"type": "float", "default": 0.0},
        "tp1": {"type": "float", "default": 0.0},
        "tp2": {"type": "float", "default": 0.0},
    },
    "initial_phase": "scanning",
    "phases": {
        # Single scanning phase — detect exhaustion at extremes
        "scanning": {
            "description": "Wait for price at extreme (near H4 strong level + BB band) with RSI extreme + Stochastic cross",
            "evaluate_on": ["H1"],
            "transitions": [
                # Bullish reversal: price near H4 support + oversold + stoch cross up
                {
                    "to": "in_long",
                    "priority": 2,
                    "conditions": {
                        "type": "AND",
                        "rules": [
                            # Price near Bollinger lower band (oversold in range)
                            {"left": "_price", "operator": "<=", "right": "ind.h1_bb.lower", "description": "Price at/below BB lower band"},
                            # RSI deeply oversold
                            {"left": "ind.h1_rsi.value", "operator": "<", "right": "30", "description": "RSI < 30 oversold"},
                            # Stochastic K crossing above D from oversold (momentum shifting)
                            {"left": "ind.h1_stoch.k", "operator": ">", "right": "ind.h1_stoch.d", "description": "Stoch K > D"},
                            {"left": "prev.h1_stoch.k", "operator": "<=", "right": "prev.h1_stoch.d", "description": "Stoch K just crossed above D"},
                            {"left": "ind.h1_stoch.k", "operator": "<", "right": "25", "description": "Stoch still in oversold zone"},
                            # MACD histogram turning up (momentum divergence)
                            {"left": "ind.h1_macd.macd", "operator": ">", "right": "prev.h1_macd.macd", "description": "MACD turning up"},
                        ]
                    },
                    "actions": [
                        {"set_var": "entry_price", "expr": "_price"},
                        {"set_var": "initial_sl", "expr": "_price - ind.h1_atr.value * 2"},
                        {"set_var": "tp1", "expr": "ind.h1_bb.middle"},
                        {"set_var": "tp2", "expr": "_price + ind.h1_atr.value * 3"},
                        {"open_trade": {
                            "direction": "BUY",
                            "sl": {"expr": "_price - ind.h1_atr.value * 2"},
                            "tp": {"expr": "_price + ind.h1_atr.value * 3"},
                        }},
                    ]
                },
                # Bearish reversal: price near H4 resistance + overbought + stoch cross down
                {
                    "to": "in_short",
                    "priority": 1,
                    "conditions": {
                        "type": "AND",
                        "rules": [
                            {"left": "_price", "operator": ">=", "right": "ind.h1_bb.upper", "description": "Price at/above BB upper band"},
                            {"left": "ind.h1_rsi.value", "operator": ">", "right": "70", "description": "RSI > 70 overbought"},
                            {"left": "ind.h1_stoch.k", "operator": "<", "right": "ind.h1_stoch.d", "description": "Stoch K < D"},
                            {"left": "prev.h1_stoch.k", "operator": ">=", "right": "prev.h1_stoch.d", "description": "Stoch K just crossed below D"},
                            {"left": "ind.h1_stoch.k", "operator": ">", "right": "75", "description": "Stoch still in overbought zone"},
                            {"left": "ind.h1_macd.macd", "operator": "<", "right": "prev.h1_macd.macd", "description": "MACD turning down"},
                        ]
                    },
                    "actions": [
                        {"set_var": "entry_price", "expr": "_price"},
                        {"set_var": "initial_sl", "expr": "_price + ind.h1_atr.value * 2"},
                        {"set_var": "tp1", "expr": "ind.h1_bb.middle"},
                        {"set_var": "tp2", "expr": "_price - ind.h1_atr.value * 3"},
                        {"open_trade": {
                            "direction": "SELL",
                            "sl": {"expr": "_price + ind.h1_atr.value * 2"},
                            "tp": {"expr": "_price - ind.h1_atr.value * 3"},
                        }},
                    ]
                },
            ],
            "timeout": None,
            "position_management": [],
            "on_trade_closed": None,
        },

        "in_long": {
            "description": "Managing long reversal trade — quick breakeven, partial at BB middle",
            "evaluate_on": ["H1"],
            "transitions": [],
            "timeout": {"bars": 40, "timeframe": "H1", "to": "scanning"},
            "position_management": [
                {
                    "name": "quick_breakeven",
                    "once": True,
                    "when": {"type": "AND", "rules": [
                        {"left": "_price", "operator": ">=", "right": "var.entry_price + ind.h1_atr.value * 1", "description": "1R profit"}
                    ]},
                    "modify_sl": {"expr": "var.entry_price + ind.h1_atr.value * 0.2"},
                },
                {
                    "name": "partial_at_bb_middle",
                    "once": True,
                    "when": {"type": "AND", "rules": [
                        {"left": "_price", "operator": ">=", "right": "var.tp1", "description": "Reached BB middle (TP1)"}
                    ]},
                    "partial_close": {"pct": 50},
                },
                {
                    "name": "trail",
                    "once": False,
                    "when": {"type": "AND", "rules": [
                        {"left": "_price", "operator": ">=", "right": "var.entry_price + ind.h1_atr.value * 2", "description": "2R"}
                    ]},
                    "trail_sl": {"distance": {"expr": "ind.h1_atr.value * 1.2"}},
                },
            ],
            "on_trade_closed": {"to": "scanning"},
        },

        "in_short": {
            "description": "Managing short reversal trade — quick breakeven, partial at BB middle",
            "evaluate_on": ["H1"],
            "transitions": [],
            "timeout": {"bars": 40, "timeframe": "H1", "to": "scanning"},
            "position_management": [
                {
                    "name": "quick_breakeven",
                    "once": True,
                    "when": {"type": "AND", "rules": [
                        {"left": "_price", "operator": "<=", "right": "var.entry_price - ind.h1_atr.value * 1", "description": "1R profit"}
                    ]},
                    "modify_sl": {"expr": "var.entry_price - ind.h1_atr.value * 0.2"},
                },
                {
                    "name": "partial_at_bb_middle",
                    "once": True,
                    "when": {"type": "AND", "rules": [
                        {"left": "_price", "operator": "<=", "right": "var.tp1", "description": "Reached BB middle (TP1)"}
                    ]},
                    "partial_close": {"pct": 50},
                },
                {
                    "name": "trail",
                    "once": False,
                    "when": {"type": "AND", "rules": [
                        {"left": "_price", "operator": "<=", "right": "var.entry_price - ind.h1_atr.value * 2", "description": "2R"}
                    ]},
                    "trail_sl": {"distance": {"expr": "ind.h1_atr.value * 1.2"}},
                },
            ],
            "on_trade_closed": {"to": "scanning"},
        },
    },
    "risk": {
        "max_lot": 0.1,
        "max_daily_trades": 6,
        "max_drawdown_pct": 4.0,
        "max_open_positions": 1,
    }
}


# ═══════════════════════════════════════════════════════════════════
# Validate and save both
# ═══════════════════════════════════════════════════════════════════

for name, playbook in [("smc_reversal_v2", smc_reversal_v2), ("divergence_reversal_v2", divergence_reversal_v2)]:
    config = PlaybookConfig(**playbook)
    print(f"Valid: {playbook['name']} | Phases: {list(config.phases.keys())} | Indicators: {[i.id for i in config.indicators]}")
    Path(f"data/playbooks/{name}.json").write_text(json.dumps(playbook, indent=2))


async def load_all():
    db = Database("data/trade_agent.db")
    await db.connect()

    for playbook in [smc_reversal_v2, divergence_reversal_v2]:
        rows = await db._db.execute_fetchall(
            "SELECT id FROM playbooks WHERE name = ?", (playbook["name"],)
        )
        if rows:
            await db._db.execute(
                "UPDATE playbooks SET config_json = ?, description_nl = ? WHERE id = ?",
                (json.dumps(playbook), playbook["description"], rows[0]["id"]),
            )
            print(f"  Updated #{rows[0]['id']}: {playbook['name']}")
        else:
            cursor = await db._db.execute(
                "INSERT INTO playbooks (name, description_nl, config_json, autonomy, enabled, explanation) VALUES (?, ?, ?, ?, 0, ?)",
                (playbook["name"], playbook["description"], json.dumps(playbook), "signal_only", ""),
            )
            print(f"  Created #{cursor.lastrowid}: {playbook['name']}")

    await db._db.commit()
    await db.disconnect()


asyncio.run(load_all())
