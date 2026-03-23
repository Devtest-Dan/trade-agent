"""Rebuild mean-reversion no-SMC playbooks from scratch."""
import json

# Start fresh from the SMC version which has correct avg band references
with open("data/playbooks/mean_reversion_div_fx.json") as f:
    data = json.load(f)

# Remove SMC rules from watching entry conditions
for pname in ["watching_short", "watching_long"]:
    for trans in data["phases"][pname]["transitions"]:
        trans["conditions"]["rules"] = [
            r for r in trans["conditions"]["rules"]
            if "h4_smc" not in r.get("left", "")
        ]

# Remove BOS danger from watching
for pname in ["watching_short", "watching_long"]:
    data["phases"][pname]["transitions"] = [
        t for t in data["phases"][pname]["transitions"]
        if not any("bos" in r.get("left", "") for r in t["conditions"]["rules"])
    ]

# Remove BOS exit from in_trade
for pname in ["in_trade_short", "in_trade_long"]:
    data["phases"][pname]["transitions"] = [
        t for t in data["phases"][pname]["transitions"]
        if not any("bos" in r.get("left", "") for r in t["conditions"]["rules"])
    ]

# Replace divergence + RSI overbought entry with RSI kernel cross + MACD
for pname in ["watching_short"]:
    for trans in data["phases"][pname]["transitions"]:
        if trans["to"] == "in_trade_short":
            trans["conditions"]["rules"] = [
                {"left": "ind.m15_rsi_kernel.rsi_cross_below", "operator": "==", "right": "1.0",
                 "description": "RSI crosses below kernel"},
                {"left": "ind.h1_macd4c.rising", "operator": "==", "right": "0.0",
                 "description": "H1 MACD falling"},
            ]

for pname in ["watching_long"]:
    for trans in data["phases"][pname]["transitions"]:
        if trans["to"] == "in_trade_long":
            trans["conditions"]["rules"] = [
                {"left": "ind.m15_rsi_kernel.rsi_cross_above", "operator": "==", "right": "1.0",
                 "description": "RSI crosses above kernel"},
                {"left": "ind.h1_macd4c.rising", "operator": "==", "right": "1.0",
                 "description": "H1 MACD rising"},
            ]

# Remove TP from trade actions
for pname in ["watching_short", "watching_long"]:
    for trans in data["phases"][pname]["transitions"]:
        if trans["to"].startswith("in_trade"):
            for action in trans["actions"]:
                if "open_trade" in action and action["open_trade"]:
                    action["open_trade"].pop("tp", None)
            trans["actions"] = [a for a in trans["actions"] if a.get("set_var") != "initial_tp"]

# Replace position management
data["phases"]["in_trade_short"]["position_management"] = [
    {
        "name": "breakeven_short", "once": True, "continuous": False,
        "when": {"type": "AND", "rules": [
            {"left": "trade.open_price - _price", "operator": ">", "right": "ind.h4_atr.value * 1.0",
             "description": "Short profit > 1x ATR"}
        ]},
        "modify_sl": {"expr": "trade.open_price"}
    },
    {
        "name": "nwe_trail_short", "once": False, "continuous": True,
        "when": {"type": "AND", "rules": [
            {"left": "trade.open_price - _price", "operator": ">", "right": "0",
             "description": "Trade in profit"},
            {"left": "ind.m15_nwe.upper_avg", "operator": "<", "right": "trade.sl",
             "description": "NWE upper_avg below SL"},
            {"left": "ind.m15_nwe.upper_avg", "operator": ">", "right": "_price * 0.9",
             "description": "Band value reasonable"}
        ]},
        "modify_sl": {"expr": "ind.m15_nwe.upper_avg"}
    }
]

data["phases"]["in_trade_long"]["position_management"] = [
    {
        "name": "breakeven_long", "once": True, "continuous": False,
        "when": {"type": "AND", "rules": [
            {"left": "_price - trade.open_price", "operator": ">", "right": "ind.h4_atr.value * 1.0",
             "description": "Long profit > 1x ATR"}
        ]},
        "modify_sl": {"expr": "trade.open_price"}
    },
    {
        "name": "nwe_trail_long", "once": False, "continuous": True,
        "when": {"type": "AND", "rules": [
            {"left": "_price - trade.open_price", "operator": ">", "right": "0",
             "description": "Trade in profit"},
            {"left": "ind.m15_nwe.lower_avg", "operator": ">", "right": "trade.sl",
             "description": "NWE lower_avg above SL"},
            {"left": "ind.m15_nwe.lower_avg", "operator": ">", "right": "_price * 0.5",
             "description": "Band value reasonable"}
        ]},
        "modify_sl": {"expr": "ind.m15_nwe.lower_avg"}
    }
]

# Add MACD indicator
ids = [i["id"] for i in data["indicators"]]
if "h1_macd4c" not in ids:
    data["indicators"].append({
        "id": "h1_macd4c", "name": "MACD_4C", "timeframe": "H1",
        "params": {"fast": 12, "slow": 26}
    })

# Re-entry
data["phases"]["in_trade_short"]["on_trade_closed"] = {"to": "watching_short"}
data["phases"]["in_trade_long"]["on_trade_closed"] = {"to": "watching_long"}

data["id"] = "mean-reversion-nosmc-fx"
data["name"] = "Mean Reversion NoSMC (FX Majors)"
data["description"] = "NWE avg band extreme + RSI kernel cross + MACD filter. No TP, NWE trailing."

with open("data/playbooks/mean_reversion_div_nosmc_fx.json", "w") as f:
    json.dump(data, f, indent=2)
print("Rebuilt nosmc FX")

# XAUUSD variant
xau = json.loads(json.dumps(data))
xau["id"] = "mean-reversion-nosmc-xauusd"
xau["name"] = "Mean Reversion NoSMC (XAUUSD)"
xau["symbols"] = ["XAUUSD"]
xau["risk"]["max_lot"] = 0.2
xau["phases"]["idle"]["transitions"] = [
    t for t in xau["phases"]["idle"]["transitions"] if t["to"] == "watching_long"
]
del xau["phases"]["watching_short"]
del xau["phases"]["in_trade_short"]

with open("data/playbooks/mean_reversion_div_nosmc_xauusd.json", "w") as f:
    json.dump(xau, f, indent=2)
print("Rebuilt nosmc XAUUSD")
