"""Journal Writer — captures full trade context for learning and refinement.

Records indicator snapshots, market context, and management events
for every trade opened and closed by the playbook engine.
"""

from datetime import datetime
from typing import Any

from loguru import logger

from agent.data_manager import DataManager
from agent.db.database import Database
from agent.models.journal import ManagementEvent, MarketContext, TradeJournalEntry
from agent.models.playbook import PlaybookConfig


# Pip value per lot for common symbols (standard lot = 100,000 units)
PIP_VALUES = {
    "XAUUSD": 0.1,  # gold: 1 pip = $0.1 per 0.01 lot
    "EURUSD": 0.0001,
    "GBPUSD": 0.0001,
    "USDJPY": 0.01,
    "AUDUSD": 0.0001,
    "USDCAD": 0.0001,
    "NZDUSD": 0.0001,
    "USDCHF": 0.0001,
}


class JournalWriter:
    """Captures trade context and writes journal entries."""

    def __init__(self, db: Database, data_manager: DataManager):
        self.db = db
        self.data_manager = data_manager
        # Active journal entries keyed by ticket number
        self._active_entries: dict[int, int] = {}  # ticket -> journal_id

    async def on_trade_opened(
        self,
        trade_id: int | None,
        signal_id: int | None,
        strategy_id: int | None,
        playbook_db_id: int | None,
        symbol: str,
        direction: str,
        lot: float,
        open_price: float,
        sl: float | None,
        tp: float | None,
        ticket: int | None,
        playbook_phase: str = "",
        variables_at_entry: dict[str, Any] | None = None,
        entry_conditions: dict[str, Any] | None = None,
        playbook_config: PlaybookConfig | None = None,
    ) -> int:
        """Record a trade opening with full indicator snapshot."""
        # Capture indicator snapshot
        entry_snapshot = self._capture_snapshot(symbol, playbook_config)

        # Capture market context
        market_ctx = self._capture_market_context(symbol)

        entry = TradeJournalEntry(
            trade_id=trade_id,
            signal_id=signal_id,
            strategy_id=strategy_id,
            playbook_db_id=playbook_db_id,
            symbol=symbol,
            direction=direction,
            lot_initial=lot,
            lot_remaining=lot,
            open_price=open_price,
            sl_initial=sl,
            tp_initial=tp,
            open_time=datetime.now(),
            playbook_phase_at_entry=playbook_phase,
            variables_at_entry=variables_at_entry or {},
            entry_snapshot=entry_snapshot,
            entry_conditions=entry_conditions or {},
            market_context=market_ctx,
        )

        journal_id = await self.db.create_journal_entry(entry)
        if ticket:
            self._active_entries[ticket] = journal_id

        logger.info(
            f"Journal entry #{journal_id} opened: {direction} {symbol} @ {open_price}"
        )
        return journal_id

    async def on_trade_closed(
        self,
        ticket: int | None,
        journal_id: int | None = None,
        close_price: float | None = None,
        pnl: float | None = None,
        exit_reason: str = "",
        sl_final: float | None = None,
        tp_final: float | None = None,
        symbol: str = "",
        playbook_config: PlaybookConfig | None = None,
    ):
        """Update journal entry on trade close with exit data."""
        # Resolve journal_id from ticket if not provided
        if journal_id is None and ticket:
            journal_id = self._active_entries.pop(ticket, None)

        if journal_id is None:
            logger.warning(f"No journal entry found for ticket {ticket}")
            return

        # Get existing entry to compute duration and outcome
        entry = await self.db.get_journal_entry(journal_id)
        if not entry:
            return

        now = datetime.now()
        duration_seconds = None
        if entry.open_time:
            open_dt = (
                datetime.fromisoformat(entry.open_time)
                if isinstance(entry.open_time, str)
                else entry.open_time
            )
            duration_seconds = int((now - open_dt).total_seconds())

        # Compute outcome
        outcome = "breakeven"
        if pnl is not None:
            if pnl > 0:
                outcome = "win"
            elif pnl < 0:
                outcome = "loss"

        # Compute R:R achieved
        rr_achieved = None
        if pnl is not None and entry.sl_initial and entry.open_price:
            risk = abs(entry.open_price - entry.sl_initial)
            if risk > 0:
                reward = abs(close_price - entry.open_price) if close_price else 0
                rr_achieved = round(reward / risk, 2)
                if pnl < 0:
                    rr_achieved = -rr_achieved

        # Compute pnl in pips
        pnl_pips = None
        if close_price and entry.open_price:
            pip_size = PIP_VALUES.get(entry.symbol or symbol, 0.0001)
            raw_pips = (close_price - entry.open_price) / pip_size
            if entry.direction == "SELL":
                raw_pips = -raw_pips
            pnl_pips = round(raw_pips, 1)

        # Capture exit snapshot
        exit_snapshot = self._capture_snapshot(
            entry.symbol or symbol, playbook_config
        )

        # Compute lot remaining
        lot_remaining = entry.lot_remaining
        if exit_reason != "partial_close":
            lot_remaining = 0.0

        updates: dict[str, Any] = {
            "close_price": close_price,
            "pnl": pnl,
            "pnl_pips": pnl_pips,
            "rr_achieved": rr_achieved,
            "outcome": outcome,
            "exit_reason": exit_reason,
            "close_time": now.isoformat(),
            "duration_seconds": duration_seconds,
            "sl_final": sl_final or entry.sl_initial,
            "tp_final": tp_final or entry.tp_initial,
            "lot_remaining": lot_remaining,
            "exit_snapshot": exit_snapshot,
        }

        await self.db.update_journal_entry(journal_id, **updates)
        logger.info(
            f"Journal entry #{journal_id} closed: {outcome} | "
            f"PnL: {pnl} | RR: {rr_achieved} | Exit: {exit_reason}"
        )

    async def on_management_event(
        self,
        ticket: int,
        rule_name: str,
        action: str,
        details: dict[str, Any] | None = None,
        phase: str = "",
    ):
        """Append a management event to the journal entry."""
        journal_id = self._active_entries.get(ticket)
        if journal_id is None:
            return

        entry = await self.db.get_journal_entry(journal_id)
        if not entry:
            return

        event = ManagementEvent(
            time=datetime.now(),
            rule_name=rule_name,
            action=action,
            details=details or {},
            phase=phase,
        )

        events = list(entry.management_events)
        events.append(event)

        await self.db.update_journal_entry(
            journal_id, management_events=events
        )

        # Update lot_remaining for partial closes
        if action == "partial_close" and details:
            pct = details.get("pct", 0)
            new_remaining = entry.lot_remaining * (1 - pct / 100) if entry.lot_remaining else None
            if new_remaining is not None:
                await self.db.update_journal_entry(journal_id, lot_remaining=new_remaining)

    def _capture_snapshot(
        self, symbol: str, playbook_config: PlaybookConfig | None = None
    ) -> dict[str, Any]:
        """Capture all indicator values for a symbol."""
        snapshot = {}

        if playbook_config:
            for ind in playbook_config.indicators:
                cached = self.data_manager.get_cached_indicator(
                    symbol, ind.timeframe, ind.id
                )
                if cached:
                    snapshot[ind.id] = {
                        "name": ind.name,
                        "timeframe": ind.timeframe,
                        "values": cached.values,
                    }
        else:
            # Fallback: collect all cached indicators for this symbol
            snapshot = self._collect_all_indicators(symbol)

        # Add current tick
        tick = self.data_manager.get_tick(symbol)
        if tick:
            snapshot["_tick"] = {
                "bid": tick.bid,
                "ask": tick.ask,
                "spread": tick.spread,
            }

        return snapshot

    def _collect_all_indicators(self, symbol: str) -> dict[str, Any]:
        """Collect all cached indicator values for a symbol."""
        result = {}
        for (s, tf, iid), iv in self.data_manager._indicators.items():
            if s == symbol:
                result[iid] = {
                    "name": iv.name,
                    "timeframe": tf,
                    "values": iv.values,
                }
        return result

    def _capture_market_context(self, symbol: str) -> MarketContext:
        """Capture current market context."""
        tick = self.data_manager.get_tick(symbol)
        spread = tick.spread if tick else None

        # Try to get ATR for volatility assessment
        atr_val = None
        atr_tf = "H1"
        for tf in ["H1", "H4", "M15"]:
            cached = self.data_manager.get_cached_indicator(symbol, tf, f"{tf.lower()}_atr")
            if cached and "value" in cached.values:
                atr_val = cached.values["value"]
                atr_tf = tf
                break

        # Determine session based on hour (UTC)
        hour = datetime.utcnow().hour
        if 0 <= hour < 8:
            session = "asian"
        elif 8 <= hour < 12:
            session = "london"
        elif 12 <= hour < 16:
            session = "overlap"
        elif 16 <= hour < 21:
            session = "newyork"
        else:
            session = "asian"

        # Determine volatility from ATR
        volatility = "normal"
        # This is a rough heuristic — would need historical ATR comparison for accuracy

        # Determine trend from structure indicator if available
        trend = "ranging"
        for tf in ["H4", "H1", "D1"]:
            smc = self.data_manager.get_cached_indicator(
                symbol, tf, f"{tf.lower()}_smc_structure"
            )
            if smc and "trend" in smc.values:
                t = smc.values["trend"]
                if t == 1:
                    trend = "bullish"
                elif t == -1:
                    trend = "bearish"
                break

        return MarketContext(
            atr=atr_val,
            atr_timeframe=atr_tf,
            session=session,
            volatility=volatility,
            trend=trend,
            spread=spread,
        )
