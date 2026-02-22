"""SQLite database layer with async support."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import aiosqlite
from loguru import logger

from agent.config import settings
from agent.models.signal import Signal, SignalDirection, SignalStatus
from agent.models.strategy import Strategy, StrategyConfig
from agent.models.trade import Trade
from agent.models.playbook import Playbook, PlaybookConfig, PlaybookState
from agent.models.journal import TradeJournalEntry, MarketContext, ManagementEvent


class Database:
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or settings.db_path
        self._db: aiosqlite.Connection | None = None

    async def connect(self):
        """Connect to SQLite and run migrations."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA synchronous=NORMAL")
        await self._db.execute(f"PRAGMA cache_size=-{settings.db_cache_mb * 1024}")
        await self._db.execute("PRAGMA temp_store=MEMORY")
        await self._db.execute("PRAGMA mmap_size=268435456")
        await self._run_migrations()
        logger.info(f"Database connected: {self.db_path}")

    async def disconnect(self):
        if self._db:
            await self._db.close()
            logger.info("Database disconnected")

    async def _run_migrations(self):
        """Run all SQL migration files."""
        # Add columns that migrations depend on BEFORE running migration scripts
        await self._add_column_if_missing("bar_cache", "bar_time_unix", "INTEGER")

        migrations_dir = Path(__file__).parent / "migrations"
        for sql_file in sorted(migrations_dir.glob("*.sql")):
            sql = sql_file.read_text()
            await self._db.executescript(sql)
        await self._db.commit()
        # Handle ALTER TABLE for columns that may not exist yet
        await self._add_column_if_missing("trades", "playbook_db_id", "INTEGER")
        await self._add_column_if_missing("trades", "journal_id", "INTEGER")
        await self._add_column_if_missing("signals", "playbook_db_id", "INTEGER")
        await self._add_column_if_missing("signals", "playbook_phase", "TEXT DEFAULT ''")
        await self._add_column_if_missing("playbooks", "explanation", "TEXT DEFAULT ''")

    async def _add_column_if_missing(self, table: str, column: str, col_type: str):
        """Add a column to a table if it doesn't already exist."""
        cursor = await self._db.execute(f"PRAGMA table_info({table})")
        columns = [row[1] for row in await cursor.fetchall()]
        if column not in columns:
            await self._db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
            await self._db.commit()
            logger.info(f"Added column {column} to {table}")

    # --- Strategies ---

    async def create_strategy(self, strategy: Strategy) -> int:
        cursor = await self._db.execute(
            """INSERT INTO strategies (name, description_nl, config_json, autonomy, enabled, risk_json)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                strategy.name,
                strategy.description_nl,
                strategy.config.model_dump_json(),
                strategy.config.autonomy.value,
                1 if strategy.enabled else 0,
                strategy.config.risk.model_dump_json(),
            ),
        )
        await self._db.commit()
        return cursor.lastrowid

    async def get_strategy(self, strategy_id: int) -> Strategy | None:
        cursor = await self._db.execute(
            "SELECT * FROM strategies WHERE id = ?", (strategy_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return self._row_to_strategy(row)

    async def list_strategies(self) -> list[Strategy]:
        cursor = await self._db.execute(
            "SELECT * FROM strategies ORDER BY created_at DESC"
        )
        rows = await cursor.fetchall()
        return [self._row_to_strategy(r) for r in rows]

    async def update_strategy(self, strategy_id: int, **kwargs) -> bool:
        sets = []
        values = []
        for key, val in kwargs.items():
            if key == "config":
                sets.append("config_json = ?")
                values.append(val.model_dump_json() if hasattr(val, 'model_dump_json') else json.dumps(val))
            elif key == "enabled":
                sets.append("enabled = ?")
                values.append(1 if val else 0)
            elif key == "autonomy":
                sets.append("autonomy = ?")
                values.append(val.value if hasattr(val, 'value') else val)
            else:
                sets.append(f"{key} = ?")
                values.append(val)
        sets.append("updated_at = ?")
        values.append(datetime.now().isoformat())
        values.append(strategy_id)

        await self._db.execute(
            f"UPDATE strategies SET {', '.join(sets)} WHERE id = ?", values
        )
        await self._db.commit()
        return True

    async def delete_strategy(self, strategy_id: int) -> bool:
        await self._db.execute("DELETE FROM strategies WHERE id = ?", (strategy_id,))
        await self._db.commit()
        return True

    def _row_to_strategy(self, row) -> Strategy:
        config_dict = json.loads(row["config_json"])
        config = StrategyConfig(**config_dict)
        return Strategy(
            id=row["id"],
            name=row["name"],
            description_nl=row["description_nl"],
            config=config,
            enabled=bool(row["enabled"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    # --- Signals ---

    async def create_signal(self, signal: Signal) -> int:
        cursor = await self._db.execute(
            """INSERT INTO signals (strategy_id, strategy_name, symbol, direction, conditions_snapshot, ai_reasoning, status, price_at_signal)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                signal.strategy_id,
                signal.strategy_name,
                signal.symbol,
                signal.direction.value,
                json.dumps(signal.conditions_snapshot),
                signal.ai_reasoning,
                signal.status.value,
                signal.price_at_signal,
            ),
        )
        await self._db.commit()
        return cursor.lastrowid

    async def update_signal_status(
        self, signal_id: int, status: SignalStatus, reasoning: str = ""
    ):
        updates = "status = ?"
        values: list[Any] = [status.value]
        if reasoning:
            updates += ", ai_reasoning = ?"
            values.append(reasoning)
        values.append(signal_id)
        await self._db.execute(
            f"UPDATE signals SET {updates} WHERE id = ?", values
        )
        await self._db.commit()

    async def list_signals(
        self,
        strategy_id: int | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Signal]:
        query = "SELECT * FROM signals WHERE 1=1"
        params: list[Any] = []
        if strategy_id is not None:
            query += " AND strategy_id = ?"
            params.append(strategy_id)
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor = await self._db.execute(query, params)
        rows = await cursor.fetchall()
        return [self._row_to_signal(r) for r in rows]

    async def get_signal(self, signal_id: int) -> Signal | None:
        cursor = await self._db.execute(
            "SELECT * FROM signals WHERE id = ?", (signal_id,)
        )
        row = await cursor.fetchone()
        return self._row_to_signal(row) if row else None

    def _row_to_signal(self, row) -> Signal:
        return Signal(
            id=row["id"],
            strategy_id=row["strategy_id"],
            strategy_name=row["strategy_name"],
            symbol=row["symbol"],
            direction=SignalDirection(row["direction"]),
            conditions_snapshot=json.loads(row["conditions_snapshot"]),
            ai_reasoning=row["ai_reasoning"],
            status=SignalStatus(row["status"]),
            price_at_signal=row["price_at_signal"],
            created_at=row["created_at"],
        )

    # --- Trades ---

    async def create_trade(self, trade: Trade) -> int:
        cursor = await self._db.execute(
            """INSERT INTO trades (signal_id, strategy_id, symbol, direction, lot, open_price, close_price, sl, tp, pnl, ticket, open_time, close_time)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                trade.signal_id,
                trade.strategy_id,
                trade.symbol,
                trade.direction,
                trade.lot,
                trade.open_price,
                trade.close_price,
                trade.sl,
                trade.tp,
                trade.pnl,
                trade.ticket,
                trade.open_time.isoformat() if trade.open_time else None,
                trade.close_time.isoformat() if trade.close_time else None,
            ),
        )
        await self._db.commit()
        return cursor.lastrowid

    async def list_trades(
        self,
        strategy_id: int | None = None,
        symbol: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Trade]:
        query = "SELECT * FROM trades WHERE 1=1"
        params: list[Any] = []
        if strategy_id is not None:
            query += " AND strategy_id = ?"
            params.append(strategy_id)
        if symbol:
            query += " AND symbol = ?"
            params.append(symbol)
        query += " ORDER BY open_time DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor = await self._db.execute(query, params)
        rows = await cursor.fetchall()
        return [self._row_to_trade(r) for r in rows]

    def _row_to_trade(self, row) -> Trade:
        return Trade(
            id=row["id"],
            signal_id=row["signal_id"],
            strategy_id=row["strategy_id"],
            symbol=row["symbol"],
            direction=row["direction"],
            lot=row["lot"],
            open_price=row["open_price"],
            close_price=row["close_price"],
            sl=row["sl"],
            tp=row["tp"],
            pnl=row["pnl"],
            ticket=row["ticket"],
            open_time=row["open_time"],
            close_time=row["close_time"],
        )

    # --- Settings ---

    async def get_setting(self, key: str) -> Any:
        cursor = await self._db.execute(
            "SELECT value_json FROM settings WHERE key = ?", (key,)
        )
        row = await cursor.fetchone()
        if row:
            return json.loads(row["value_json"])
        return None

    async def set_setting(self, key: str, value: Any):
        await self._db.execute(
            """INSERT INTO settings (key, value_json) VALUES (?, ?)
               ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json""",
            (key, json.dumps(value)),
        )
        await self._db.commit()

    # --- Playbooks ---

    async def create_playbook(self, playbook: Playbook) -> int:
        cursor = await self._db.execute(
            """INSERT INTO playbooks (name, description_nl, explanation, config_json, autonomy, enabled)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                playbook.name,
                playbook.description_nl,
                playbook.explanation,
                playbook.config.model_dump_json(by_alias=True),
                playbook.config.autonomy.value,
                1 if playbook.enabled else 0,
            ),
        )
        await self._db.commit()
        return cursor.lastrowid

    async def get_playbook(self, playbook_id: int) -> Playbook | None:
        cursor = await self._db.execute(
            "SELECT * FROM playbooks WHERE id = ?", (playbook_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return self._row_to_playbook(row)

    async def list_playbooks(self) -> list[Playbook]:
        cursor = await self._db.execute(
            "SELECT * FROM playbooks ORDER BY created_at DESC"
        )
        rows = await cursor.fetchall()
        return [self._row_to_playbook(r) for r in rows]

    async def update_playbook(self, playbook_id: int, **kwargs) -> bool:
        sets = []
        values = []
        for key, val in kwargs.items():
            if key == "config":
                sets.append("config_json = ?")
                values.append(
                    val.model_dump_json(by_alias=True)
                    if hasattr(val, "model_dump_json")
                    else json.dumps(val)
                )
            elif key == "enabled":
                sets.append("enabled = ?")
                values.append(1 if val else 0)
            elif key == "autonomy":
                sets.append("autonomy = ?")
                values.append(val.value if hasattr(val, "value") else val)
            else:
                sets.append(f"{key} = ?")
                values.append(val)
        sets.append("updated_at = ?")
        values.append(datetime.now().isoformat())
        values.append(playbook_id)

        await self._db.execute(
            f"UPDATE playbooks SET {', '.join(sets)} WHERE id = ?", values
        )
        await self._db.commit()
        return True

    async def create_playbook_version(
        self, playbook_id: int, config_json: str, source: str = "manual", notes: str = ""
    ) -> int:
        """Save a new version of a playbook config."""
        # Get next version number
        cursor = await self._db.execute(
            "SELECT COALESCE(MAX(version), 0) + 1 FROM playbook_versions WHERE playbook_id = ?",
            (playbook_id,),
        )
        row = await cursor.fetchone()
        next_version = row[0]

        cursor = await self._db.execute(
            """INSERT INTO playbook_versions (playbook_id, version, config_json, source, notes)
               VALUES (?, ?, ?, ?, ?)""",
            (playbook_id, next_version, config_json, source, notes),
        )
        await self._db.commit()
        return next_version

    async def list_playbook_versions(self, playbook_id: int) -> list[dict]:
        """List all versions of a playbook (newest first)."""
        cursor = await self._db.execute(
            """SELECT id, playbook_id, version, source, notes, created_at
               FROM playbook_versions WHERE playbook_id = ? ORDER BY version DESC""",
            (playbook_id,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def get_playbook_version(self, playbook_id: int, version: int) -> dict | None:
        """Get a specific version's config."""
        cursor = await self._db.execute(
            "SELECT * FROM playbook_versions WHERE playbook_id = ? AND version = ?",
            (playbook_id, version),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return dict(row)

    async def delete_playbook(self, playbook_id: int) -> bool:
        await self._db.execute("DELETE FROM playbook_state WHERE playbook_id = ?", (playbook_id,))
        await self._db.execute("DELETE FROM playbooks WHERE id = ?", (playbook_id,))
        await self._db.commit()
        return True

    def _row_to_playbook(self, row) -> Playbook:
        config_dict = json.loads(row["config_json"])
        config = PlaybookConfig(**config_dict)
        return Playbook(
            id=row["id"],
            name=row["name"],
            description_nl=row["description_nl"],
            explanation=row["explanation"] if "explanation" in row.keys() else "",
            config=config,
            enabled=bool(row["enabled"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    # --- Playbook State ---

    async def get_playbook_state(self, playbook_id: int, symbol: str) -> PlaybookState | None:
        cursor = await self._db.execute(
            "SELECT * FROM playbook_state WHERE playbook_id = ? AND symbol = ?",
            (playbook_id, symbol),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return PlaybookState(
            playbook_id=row["playbook_id"],
            symbol=row["symbol"],
            current_phase=row["current_phase"],
            variables=json.loads(row["variables_json"]),
            bars_in_phase=row["bars_in_phase"],
            phase_timeframe_bars=json.loads(row["phase_timeframe_bars_json"]),
            fired_once_rules=json.loads(row["fired_once_rules_json"]),
            open_ticket=row["open_ticket"],
            open_direction=row["open_direction"],
            updated_at=row["updated_at"],
        )

    async def save_playbook_state(self, state: PlaybookState):
        await self._db.execute(
            """INSERT INTO playbook_state
               (playbook_id, symbol, current_phase, variables_json, bars_in_phase,
                phase_timeframe_bars_json, fired_once_rules_json, open_ticket, open_direction, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(playbook_id, symbol) DO UPDATE SET
                 current_phase = excluded.current_phase,
                 variables_json = excluded.variables_json,
                 bars_in_phase = excluded.bars_in_phase,
                 phase_timeframe_bars_json = excluded.phase_timeframe_bars_json,
                 fired_once_rules_json = excluded.fired_once_rules_json,
                 open_ticket = excluded.open_ticket,
                 open_direction = excluded.open_direction,
                 updated_at = excluded.updated_at""",
            (
                state.playbook_id,
                state.symbol,
                state.current_phase,
                json.dumps(state.variables),
                state.bars_in_phase,
                json.dumps(state.phase_timeframe_bars),
                json.dumps(state.fired_once_rules),
                state.open_ticket,
                state.open_direction,
                datetime.now().isoformat(),
            ),
        )
        await self._db.commit()

    async def delete_playbook_state(self, playbook_id: int, symbol: str):
        await self._db.execute(
            "DELETE FROM playbook_state WHERE playbook_id = ? AND symbol = ?",
            (playbook_id, symbol),
        )
        await self._db.commit()

    # --- Trade Journal ---

    async def create_journal_entry(self, entry: TradeJournalEntry) -> int:
        cursor = await self._db.execute(
            """INSERT INTO trade_journal
               (trade_id, signal_id, strategy_id, playbook_db_id, symbol, direction,
                lot_initial, lot_remaining, open_price, close_price, sl_initial, tp_initial,
                sl_final, tp_final, open_time, close_time, duration_seconds, bars_held,
                pnl, pnl_pips, rr_achieved, outcome, exit_reason,
                playbook_phase_at_entry, variables_at_entry_json,
                entry_snapshot_json, exit_snapshot_json,
                entry_conditions_json, exit_conditions_json,
                market_context_json, management_events_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                entry.trade_id,
                entry.signal_id,
                entry.strategy_id,
                entry.playbook_db_id,
                entry.symbol,
                entry.direction,
                entry.lot_initial,
                entry.lot_remaining,
                entry.open_price,
                entry.close_price,
                entry.sl_initial,
                entry.tp_initial,
                entry.sl_final,
                entry.tp_final,
                entry.open_time.isoformat() if entry.open_time else None,
                entry.close_time.isoformat() if entry.close_time else None,
                entry.duration_seconds,
                entry.bars_held,
                entry.pnl,
                entry.pnl_pips,
                entry.rr_achieved,
                entry.outcome,
                entry.exit_reason,
                entry.playbook_phase_at_entry,
                json.dumps(entry.variables_at_entry),
                json.dumps(entry.entry_snapshot),
                json.dumps(entry.exit_snapshot),
                json.dumps(entry.entry_conditions),
                json.dumps(entry.exit_conditions),
                entry.market_context.model_dump_json() if entry.market_context else "{}",
                json.dumps([e.model_dump() for e in entry.management_events], default=str),
            ),
        )
        await self._db.commit()
        return cursor.lastrowid

    async def update_journal_entry(self, journal_id: int, **kwargs) -> bool:
        sets = []
        values = []
        for key, val in kwargs.items():
            if key in (
                "variables_at_entry", "entry_snapshot", "exit_snapshot",
                "entry_conditions", "exit_conditions",
            ):
                sets.append(f"{key}_json = ?")
                values.append(json.dumps(val))
            elif key == "market_context":
                sets.append("market_context_json = ?")
                values.append(val.model_dump_json() if hasattr(val, "model_dump_json") else json.dumps(val))
            elif key == "management_events":
                sets.append("management_events_json = ?")
                values.append(json.dumps([e.model_dump() for e in val] if val else [], default=str))
            elif key in ("open_time", "close_time"):
                sets.append(f"{key} = ?")
                values.append(val.isoformat() if hasattr(val, "isoformat") else val)
            else:
                sets.append(f"{key} = ?")
                values.append(val)
        values.append(journal_id)

        await self._db.execute(
            f"UPDATE trade_journal SET {', '.join(sets)} WHERE id = ?", values
        )
        await self._db.commit()
        return True

    async def get_journal_entry(self, journal_id: int) -> TradeJournalEntry | None:
        cursor = await self._db.execute(
            "SELECT * FROM trade_journal WHERE id = ?", (journal_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return self._row_to_journal(row)

    async def list_journal_entries(
        self,
        playbook_db_id: int | None = None,
        strategy_id: int | None = None,
        symbol: str | None = None,
        outcome: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[TradeJournalEntry]:
        query = "SELECT * FROM trade_journal WHERE 1=1"
        params: list[Any] = []
        if playbook_db_id is not None:
            query += " AND playbook_db_id = ?"
            params.append(playbook_db_id)
        if strategy_id is not None:
            query += " AND strategy_id = ?"
            params.append(strategy_id)
        if symbol:
            query += " AND symbol = ?"
            params.append(symbol)
        if outcome:
            query += " AND outcome = ?"
            params.append(outcome)
        query += " ORDER BY open_time DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor = await self._db.execute(query, params)
        rows = await cursor.fetchall()
        return [self._row_to_journal(r) for r in rows]

    async def get_journal_analytics(
        self,
        playbook_db_id: int | None = None,
        strategy_id: int | None = None,
        symbol: str | None = None,
    ) -> dict[str, Any]:
        """Aggregate journal analytics: win rate, avg PnL, avg RR, etc."""
        where = "WHERE 1=1"
        params: list[Any] = []
        if playbook_db_id is not None:
            where += " AND playbook_db_id = ?"
            params.append(playbook_db_id)
        if strategy_id is not None:
            where += " AND strategy_id = ?"
            params.append(strategy_id)
        if symbol:
            where += " AND symbol = ?"
            params.append(symbol)

        cursor = await self._db.execute(
            f"""SELECT
                COUNT(*) as total,
                SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN outcome = 'loss' THEN 1 ELSE 0 END) as losses,
                SUM(CASE WHEN outcome = 'breakeven' THEN 1 ELSE 0 END) as breakevens,
                AVG(pnl) as avg_pnl,
                SUM(pnl) as total_pnl,
                AVG(pnl_pips) as avg_pips,
                AVG(rr_achieved) as avg_rr,
                MAX(pnl) as best_trade,
                MIN(pnl) as worst_trade,
                AVG(duration_seconds) as avg_duration,
                AVG(bars_held) as avg_bars
            FROM trade_journal {where}""",
            params,
        )
        row = await cursor.fetchone()
        total = row["total"] or 0
        wins = row["wins"] or 0

        # Exit reason breakdown
        cursor2 = await self._db.execute(
            f"SELECT exit_reason, COUNT(*) as cnt FROM trade_journal {where} GROUP BY exit_reason",
            params,
        )
        exit_reasons = {r["exit_reason"]: r["cnt"] for r in await cursor2.fetchall() if r["exit_reason"]}

        return {
            "total_trades": total,
            "wins": wins,
            "losses": row["losses"] or 0,
            "breakevens": row["breakevens"] or 0,
            "win_rate": round(wins / total * 100, 1) if total > 0 else 0,
            "avg_pnl": round(row["avg_pnl"] or 0, 2),
            "total_pnl": round(row["total_pnl"] or 0, 2),
            "avg_pips": round(row["avg_pips"] or 0, 1),
            "avg_rr": round(row["avg_rr"] or 0, 2),
            "best_trade": round(row["best_trade"] or 0, 2),
            "worst_trade": round(row["worst_trade"] or 0, 2),
            "avg_duration_seconds": int(row["avg_duration"] or 0),
            "avg_bars_held": round(row["avg_bars"] or 0, 1),
            "exit_reasons": exit_reasons,
        }

    async def get_journal_condition_analytics(
        self, playbook_db_id: int | None = None
    ) -> list[dict]:
        """Per-condition win rates from entry conditions JSON."""
        where = "WHERE entry_conditions_json != '{}'"
        params: list[Any] = []
        if playbook_db_id is not None:
            where += " AND playbook_db_id = ?"
            params.append(playbook_db_id)

        cursor = await self._db.execute(
            f"SELECT entry_conditions_json, outcome FROM trade_journal {where}",
            params,
        )
        rows = await cursor.fetchall()

        # Aggregate by condition key
        condition_stats: dict[str, dict] = {}
        for row in rows:
            conditions = json.loads(row["entry_conditions_json"])
            outcome = row["outcome"]
            for key, val in conditions.items():
                if key not in condition_stats:
                    condition_stats[key] = {"total": 0, "wins": 0, "losses": 0}
                condition_stats[key]["total"] += 1
                if outcome == "win":
                    condition_stats[key]["wins"] += 1
                elif outcome == "loss":
                    condition_stats[key]["losses"] += 1

        results = []
        for key, stats in condition_stats.items():
            total = stats["total"]
            results.append({
                "condition": key,
                "total": total,
                "wins": stats["wins"],
                "losses": stats["losses"],
                "win_rate": round(stats["wins"] / total * 100, 1) if total > 0 else 0,
            })
        results.sort(key=lambda x: x["total"], reverse=True)
        return results

    def _row_to_journal(self, row) -> TradeJournalEntry:
        mc_json = json.loads(row["market_context_json"]) if row["market_context_json"] else {}
        market_ctx = MarketContext(**mc_json) if mc_json else None

        events_json = json.loads(row["management_events_json"]) if row["management_events_json"] else []
        events = [ManagementEvent(**e) for e in events_json]

        return TradeJournalEntry(
            id=row["id"],
            trade_id=row["trade_id"],
            signal_id=row["signal_id"],
            strategy_id=row["strategy_id"],
            playbook_db_id=row["playbook_db_id"],
            symbol=row["symbol"],
            direction=row["direction"],
            lot_initial=row["lot_initial"],
            lot_remaining=row["lot_remaining"],
            open_price=row["open_price"],
            close_price=row["close_price"],
            sl_initial=row["sl_initial"],
            tp_initial=row["tp_initial"],
            sl_final=row["sl_final"],
            tp_final=row["tp_final"],
            open_time=row["open_time"],
            close_time=row["close_time"],
            duration_seconds=row["duration_seconds"],
            bars_held=row["bars_held"],
            pnl=row["pnl"],
            pnl_pips=row["pnl_pips"],
            rr_achieved=row["rr_achieved"],
            outcome=row["outcome"],
            exit_reason=row["exit_reason"],
            playbook_phase_at_entry=row["playbook_phase_at_entry"],
            variables_at_entry=json.loads(row["variables_at_entry_json"]),
            entry_snapshot=json.loads(row["entry_snapshot_json"]),
            exit_snapshot=json.loads(row["exit_snapshot_json"]),
            entry_conditions=json.loads(row["entry_conditions_json"]),
            exit_conditions=json.loads(row["exit_conditions_json"]),
            market_context=market_ctx,
            management_events=events,
            created_at=row["created_at"],
        )

    # --- Build Sessions ---

    async def create_build_session(
        self,
        playbook_id: int | None,
        natural_language: str,
        skills_used: list[str],
        model_used: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        duration_ms: int = 0,
    ) -> int:
        cursor = await self._db.execute(
            """INSERT INTO build_sessions
               (playbook_id, natural_language, skills_used, model_used,
                prompt_tokens, completion_tokens, duration_ms)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                playbook_id,
                natural_language,
                json.dumps(skills_used),
                model_used,
                prompt_tokens,
                completion_tokens,
                duration_ms,
            ),
        )
        await self._db.commit()
        return cursor.lastrowid

    # --- Backtest Runs ---

    async def create_backtest_run(self, run) -> int:
        cursor = await self._db.execute(
            """INSERT INTO backtest_runs (playbook_id, symbol, timeframe, bar_count, status, config_json)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                run.playbook_id,
                run.symbol,
                run.timeframe,
                run.bar_count,
                run.status,
                run.config.model_dump_json() if run.config else "{}",
            ),
        )
        await self._db.commit()
        return cursor.lastrowid

    async def update_backtest_run(self, run_id: int, **kwargs) -> bool:
        sets = []
        values = []
        for key, val in kwargs.items():
            if key in ("config_json", "result_json"):
                sets.append(f"{key} = ?")
                values.append(val)
            elif key == "config":
                sets.append("config_json = ?")
                values.append(val.model_dump_json() if hasattr(val, "model_dump_json") else json.dumps(val))
            elif key == "result":
                sets.append("result_json = ?")
                values.append(val.model_dump_json() if hasattr(val, "model_dump_json") else json.dumps(val))
            else:
                sets.append(f"{key} = ?")
                values.append(val)
        values.append(run_id)
        await self._db.execute(
            f"UPDATE backtest_runs SET {', '.join(sets)} WHERE id = ?", values
        )
        await self._db.commit()
        return True

    async def get_backtest_run(self, run_id: int) -> dict | None:
        cursor = await self._db.execute(
            "SELECT * FROM backtest_runs WHERE id = ?", (run_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "playbook_id": row["playbook_id"],
            "symbol": row["symbol"],
            "timeframe": row["timeframe"],
            "bar_count": row["bar_count"],
            "status": row["status"],
            "config": json.loads(row["config_json"]) if row["config_json"] else {},
            "result": json.loads(row["result_json"]) if row["result_json"] else None,
            "created_at": row["created_at"],
        }

    async def list_backtest_runs(self, playbook_id: int | None = None, limit: int = 50, offset: int = 0) -> list[dict]:
        query = "SELECT * FROM backtest_runs WHERE 1=1"
        params: list[Any] = []
        if playbook_id is not None:
            query += " AND playbook_id = ?"
            params.append(playbook_id)
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        cursor = await self._db.execute(query, params)
        rows = await cursor.fetchall()
        results = []
        for row in rows:
            results.append({
                "id": row["id"],
                "playbook_id": row["playbook_id"],
                "symbol": row["symbol"],
                "timeframe": row["timeframe"],
                "bar_count": row["bar_count"],
                "status": row["status"],
                "config": json.loads(row["config_json"]) if row["config_json"] else {},
                "result": json.loads(row["result_json"]) if row["result_json"] else None,
                "created_at": row["created_at"],
            })
        return results

    async def delete_backtest_run(self, run_id: int) -> bool:
        await self._db.execute("DELETE FROM backtest_trades WHERE run_id = ?", (run_id,))
        await self._db.execute("DELETE FROM backtest_runs WHERE id = ?", (run_id,))
        await self._db.commit()
        return True

    async def create_backtest_trade(self, run_id: int, trade) -> int:
        cursor = await self._db.execute(
            """INSERT INTO backtest_trades
               (run_id, direction, open_bar_idx, close_bar_idx, open_price, close_price,
                open_time, close_time, sl, tp, lot, pnl, pnl_pips, rr_achieved,
                outcome, exit_reason, phase_at_entry, variables_at_entry_json, entry_indicators_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run_id,
                trade.direction,
                trade.open_idx,
                trade.close_idx,
                trade.open_price,
                trade.close_price,
                trade.open_time,
                trade.close_time,
                trade.sl,
                trade.tp,
                trade.lot,
                trade.pnl,
                trade.pnl_pips,
                trade.rr_achieved,
                trade.outcome,
                trade.exit_reason,
                trade.phase_at_entry,
                json.dumps(trade.variables_at_entry),
                json.dumps(trade.entry_indicators),
            ),
        )
        await self._db.commit()
        return cursor.lastrowid

    async def create_backtest_trades_batch(self, run_id: int, trades: list) -> None:
        """Insert multiple backtest trades in a single transaction (executemany)."""
        rows = [
            (
                run_id,
                t.direction,
                t.open_idx,
                t.close_idx,
                t.open_price,
                t.close_price,
                t.open_time,
                t.close_time,
                t.sl,
                t.tp,
                t.lot,
                t.pnl,
                t.pnl_pips,
                t.rr_achieved,
                t.outcome,
                t.exit_reason,
                t.phase_at_entry,
                json.dumps(t.variables_at_entry),
                json.dumps(t.entry_indicators),
            )
            for t in trades
        ]
        await self._db.executemany(
            """INSERT INTO backtest_trades
               (run_id, direction, open_bar_idx, close_bar_idx, open_price, close_price,
                open_time, close_time, sl, tp, lot, pnl, pnl_pips, rr_achieved,
                outcome, exit_reason, phase_at_entry, variables_at_entry_json, entry_indicators_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
        await self._db.commit()

    async def list_backtest_trades(self, run_id: int) -> list[dict]:
        cursor = await self._db.execute(
            "SELECT * FROM backtest_trades WHERE run_id = ? ORDER BY open_bar_idx",
            (run_id,),
        )
        rows = await cursor.fetchall()
        return [
            {
                "id": row["id"],
                "run_id": row["run_id"],
                "direction": row["direction"],
                "open_bar_idx": row["open_bar_idx"],
                "close_bar_idx": row["close_bar_idx"],
                "open_price": row["open_price"],
                "close_price": row["close_price"],
                "open_time": row["open_time"],
                "close_time": row["close_time"],
                "sl": row["sl"],
                "tp": row["tp"],
                "lot": row["lot"],
                "pnl": row["pnl"],
                "pnl_pips": row["pnl_pips"],
                "rr_achieved": row["rr_achieved"],
                "outcome": row["outcome"],
                "exit_reason": row["exit_reason"],
                "phase_at_entry": row["phase_at_entry"],
                "variables_at_entry": json.loads(row["variables_at_entry_json"]) if row["variables_at_entry_json"] else {},
                "entry_indicators": json.loads(row["entry_indicators_json"]) if row["entry_indicators_json"] else {},
            }
            for row in rows
        ]
