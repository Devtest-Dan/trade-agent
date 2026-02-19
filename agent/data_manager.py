"""Data Manager — buffers OHLCV bars and indicator values per symbol/timeframe."""

import asyncio
from collections import defaultdict
from datetime import datetime
from typing import Any, Callable

from loguru import logger

from agent.bridge import ZMQBridge
from agent.models.market import Bar, IndicatorValue, MarketSnapshot, Tick

# Map timeframe strings to seconds for bar-close detection
TF_SECONDS = {
    "M1": 60,
    "M5": 300,
    "M15": 900,
    "M30": 1800,
    "H1": 3600,
    "H4": 14400,
    "D1": 86400,
    "W1": 604800,
}


class DataManager:
    def __init__(self, bridge: ZMQBridge, max_bars: int = 200):
        self.bridge = bridge
        self.max_bars = max_bars

        # Buffers: {(symbol, timeframe): [Bar, ...]}
        self._bars: dict[tuple[str, str], list[Bar]] = defaultdict(list)

        # Indicator cache: {(symbol, timeframe, indicator_id): IndicatorValue}
        self._indicators: dict[tuple[str, str, str], IndicatorValue] = {}

        # Latest ticks: {symbol: Tick}
        self._ticks: dict[str, Tick] = {}

        # Last known bar time per (symbol, tf) — for detecting bar closes
        self._last_bar_time: dict[tuple[str, str]] = {}

        # Callbacks for bar close events
        self._bar_close_callbacks: list[Callable] = []

        # Subscribed timeframes per symbol
        self._subscriptions: dict[str, set[str]] = defaultdict(set)

    def subscribe(self, symbol: str, timeframes: list[str]):
        """Register interest in a symbol's timeframes."""
        self._subscriptions[symbol].update(timeframes)

    def on_bar_close(self, callback: Callable):
        """Register callback for bar close events: callback(symbol, timeframe)."""
        self._bar_close_callbacks.append(callback)

    async def initialize(self, symbol: str, timeframes: list[str], bar_count: int = 100):
        """Pre-fetch bars for all subscribed timeframes."""
        self.subscribe(symbol, timeframes)
        for tf in timeframes:
            bars = await self.bridge.get_bars(symbol, tf, bar_count)
            if bars:
                self._bars[(symbol, tf)] = bars[-self.max_bars :]
                self._last_bar_time[(symbol, tf)] = bars[-1].time
                logger.info(f"Loaded {len(bars)} bars for {symbol}/{tf}")

    async def on_tick(self, tick: Tick):
        """Process incoming tick — update cache and check for bar closes."""
        self._ticks[tick.symbol] = tick

        # Check if any subscribed timeframe has a new bar
        for tf in self._subscriptions.get(tick.symbol, []):
            await self._check_new_bar(tick.symbol, tf)

    async def _check_new_bar(self, symbol: str, timeframe: str):
        """Check if a new bar has formed for this symbol/timeframe."""
        key = (symbol, timeframe)
        bars = await self.bridge.get_bars(symbol, timeframe, 2)
        if not bars:
            return

        latest = bars[-1]
        prev_time = self._last_bar_time.get(key)

        if prev_time is None or latest.time > prev_time:
            self._last_bar_time[key] = latest.time

            # Append new bar to buffer
            buf = self._bars[key]
            if not buf or buf[-1].time < latest.time:
                buf.append(latest)
                if len(buf) > self.max_bars:
                    self._bars[key] = buf[-self.max_bars :]

            # Skip first-time detection (initialization)
            if prev_time is not None:
                logger.debug(f"New bar closed: {symbol}/{timeframe} at {latest.time}")
                for cb in self._bar_close_callbacks:
                    try:
                        result = cb(symbol, timeframe)
                        if asyncio.iscoroutine(result):
                            await result
                    except Exception as e:
                        logger.error(f"Bar close callback error: {e}")

    async def fetch_indicator(
        self,
        indicator_id: str,
        name: str,
        symbol: str,
        timeframe: str,
        params: dict[str, Any],
    ) -> IndicatorValue | None:
        """Fetch indicator from MT5 and cache it."""
        values = await self.bridge.get_indicator(symbol, timeframe, name, params, count=3)
        if not values:
            return None

        # Get the most recent value for each output buffer
        latest_values = {}
        for buf_name, buf_vals in values.items():
            if isinstance(buf_vals, list) and buf_vals:
                latest_values[buf_name] = buf_vals[0]  # index 0 = current bar
            elif isinstance(buf_vals, (int, float)):
                latest_values[buf_name] = float(buf_vals)

        bars = self._bars.get((symbol, timeframe), [])
        bar_time = bars[-1].time if bars else datetime.now()

        iv = IndicatorValue(
            indicator_id=indicator_id,
            name=name,
            symbol=symbol,
            timeframe=timeframe,
            params=params,
            values=latest_values,
            bar_time=bar_time,
        )

        self._indicators[(symbol, timeframe, indicator_id)] = iv
        return iv

    def get_cached_indicator(
        self, symbol: str, timeframe: str, indicator_id: str
    ) -> IndicatorValue | None:
        """Get cached indicator value."""
        return self._indicators.get((symbol, timeframe, indicator_id))

    def get_tick(self, symbol: str) -> Tick | None:
        return self._ticks.get(symbol)

    def get_bars(self, symbol: str, timeframe: str) -> list[Bar]:
        return self._bars.get((symbol, timeframe), [])

    def get_snapshot(self, symbol: str, timeframe: str) -> MarketSnapshot:
        """Get full market snapshot for a symbol/timeframe."""
        indicators = {}
        for (s, tf, iid), iv in self._indicators.items():
            if s == symbol and tf == timeframe:
                indicators[iid] = iv

        return MarketSnapshot(
            symbol=symbol,
            timeframe=timeframe,
            tick=self._ticks.get(symbol),
            bars=self._bars.get((symbol, timeframe), []),
            indicators=indicators,
        )

    async def refresh_indicators(
        self, symbol: str, timeframe: str, indicators: list[dict]
    ):
        """Refresh all indicator values for a symbol/timeframe."""
        for ind in indicators:
            if ind.get("timeframe") == timeframe:
                await self.fetch_indicator(
                    indicator_id=ind["id"],
                    name=ind["name"],
                    symbol=symbol,
                    timeframe=timeframe,
                    params=ind.get("params", {}),
                )
