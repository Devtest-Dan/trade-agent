# {Indicator Name} — Playbook Skills

## Overview
Brief description of what this indicator measures and its primary use cases.

## When to Use
- Market conditions where this indicator excels
- Best timeframes for different purposes
- XAUUSD-specific considerations

## Parameters Guide
| Parameter | Default | Effect of Lower | Effect of Higher | XAUUSD Recommendation |
|-----------|---------|-----------------|------------------|-----------------------|
| period | 14 | More sensitive, more noise | Smoother, more lag | ... |

## Key Patterns & Setups

### Pattern 1: {Name}
**Description:** What the pattern looks like and what it means.

**Playbook conditions:**
```json
{
  "type": "AND",
  "rules": [
    {"left": "ind.{id}.{field}", "operator": "<", "right": "30", "description": "..."}
  ]
}
```

### Pattern 2: {Name}
...

## Combinations
Which indicators pair well with this one and why.

| Combo | Purpose | Confluence Type |
|-------|---------|-----------------|
| + ATR | Volatility-adjusted stops | SL/TP sizing |
| + EMA | Trend confirmation | Filter |

## Position Management
How to use this indicator for dynamic SL/TP, trailing, and partial closes.

### Dynamic SL
```json
{"expr": "ind.{id}.{field} - ind.h4_atr.value * 1.5"}
```

### Trailing Stop
When and how to trail using this indicator.

## Pitfalls
- Common mistake 1 and how to avoid it
- Common mistake 2 and how to avoid it

## XAUUSD-Specific Notes
Gold-specific tuning recommendations, session considerations, and volatility adjustments.
