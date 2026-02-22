# KeltnerChannel — Playbook Skills

## Overview
Keltner Channel wraps an Exponential Moving Average (EMA) with upper and lower bands offset by a multiple of the Average True Range (ATR). It combines trend direction (EMA slope) with volatility measurement (ATR width) into a single overlay, making it useful for both breakout and mean-reversion strategies.

## When to Use
- **Trend-following breakouts** — price closing above the upper band signals strong bullish momentum; below the lower band signals bearish momentum.
- **Mean-reversion entries** — price returning inside the channel after a brief excursion can signal a pullback entry in the direction of the trend.
- **Volatility filtering** — the `width` output (band spread as % of price) tells you whether the market is in a compressed or expanded volatility state. Narrow width often precedes large moves.
- **Squeeze detection** — combine with Bollinger Bands; when Bollinger Bands contract inside Keltner bands a "squeeze" is in effect, signaling an imminent expansion.

## Parameters Guide
| Parameter    | Default | Effect of Lower        | Effect of Higher         | Recommendation                           |
|------------- |---------|------------------------|--------------------------|------------------------------------------|
| ema_period   | 20      | More responsive, noisier channel | Smoother, slower to react | 20 for swing trading; 10-15 for scalping |
| atr_period   | 10      | ATR reacts faster to recent volatility | ATR smooths out spikes   | Keep ≤ ema_period; 10 is standard        |
| atr_factor   | 2.0     | Tighter bands, more frequent touches | Wider bands, only extreme moves break out | 1.5 for mean-reversion; 2.0-2.5 for breakouts |

## Key Patterns & Setups

### 1. Channel Breakout (Momentum)
- **Signal:** Close above `upper` → bullish; close below `lower` → bearish.
- **Confirmation:** Rising `width` confirms genuine expansion, not just a spike.
- **Entry:** On the candle that closes outside the band.
- **Stop:** Middle line (EMA) or the opposite band.

### 2. Channel Walk
- **Signal:** Price hugs the upper or lower band for multiple bars while EMA slopes in the same direction.
- **Interpretation:** Strong sustained trend — do not fade.
- **Exit:** When price crosses back through the middle line.

### 3. Mean-Reversion Touch
- **Signal:** Price tags the upper/lower band but closes back inside.
- **Confirmation:** EMA is flat or sloping against the touch direction; `width` is not expanding.
- **Entry:** On the close back inside the band.
- **Target:** Middle line (EMA) or the opposite band.

### 4. Squeeze Setup
- **Signal:** `width` contracts to unusually low levels (look for the lowest width in the past 50-100 bars).
- **Interpretation:** Volatility compression — expect a breakout. Direction is unknown until the break occurs.
- **Entry:** On the first close outside a band after the squeeze.

## Combinations
| Combine With      | Purpose                                                    |
|-------------------|------------------------------------------------------------|
| RSI               | Confirm overbought/oversold at band touches for mean-reversion |
| MACD              | Confirm momentum direction on channel breakouts            |
| Bollinger Bands   | Detect squeeze (BB inside KC = squeeze active)             |
| Volume / OBV      | Validate breakouts with volume expansion                   |
| ATR (standalone)  | Set stop-loss distances relative to current volatility     |
| ADX               | Filter: only take breakouts when ADX > 20                  |

## Position Management
- **Stop-loss:** Place just beyond the opposite band or 1× ATR beyond entry for breakout trades.
- **Trailing stop:** Trail using the middle line (EMA) for trend-following; trail with the opposite band for aggressive targets.
- **Take-profit:** Middle line for mean-reversion trades; 1.5-2× channel width projection for breakout trades.
- **Position sizing:** Use the `width` output to scale position size inversely to volatility — wider channel = smaller position.

## Pitfalls
- **Choppy / ranging markets:** Channel breakouts produce many false signals when the market is ranging. Filter with ADX or check that EMA is sloping.
- **Fat-finger / gap spikes:** A single large candle can temporarily widen ATR and distort the bands for several bars.
- **Lagging nature:** EMA and ATR are both lagging. Keltner Channel confirms moves rather than predicting them — do not front-run.
- **Over-optimization of factor:** Backtesting often overfits the ATR multiplier to a specific regime. Stick to the 1.5 – 2.5 range.
- **Confusing with Bollinger Bands:** Keltner uses ATR (volatility of range), Bollinger uses standard deviation (volatility of close). They behave differently in trending vs. ranging markets.