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
        await self._run_migrations()
        logger.info(f"Database connected: {self.db_path}")

    async def disconnect(self):
        if self._db:
            await self._db.close()
            logger.info("Database disconnected")

    async def _run_migrations(self):
        """Run all SQL migration files."""
        migrations_dir = Path(__file__).parent / "migrations"
        for sql_file in sorted(migrations_dir.glob("*.sql")):
            sql = sql_file.read_text()
            await self._db.executescript(sql)
        await self._db.commit()

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
