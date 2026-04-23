"""
Database initialization and schema management.
Uses SQLite with aiosqlite for async access.

Schema is kept simple for V1 — everything is JSON blobs with indexed key columns.
This makes it easy to query and extend without migrations.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import aiosqlite
from loguru import logger


DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS tokens (
    mint            TEXT PRIMARY KEY,
    source          TEXT,
    state           TEXT,
    first_seen_ts   REAL,
    liquidity_usd   REAL,
    suspicious_score REAL,
    reject_reason   TEXT,
    data            TEXT,   -- full JSON blob
    updated_at      REAL DEFAULT (unixepoch('now'))
);

CREATE TABLE IF NOT EXISTS positions (
    position_id     TEXT PRIMARY KEY,
    mint            TEXT NOT NULL,
    mode            TEXT NOT NULL,
    strategy_id     TEXT,
    strategy_name   TEXT,
    ledger_type     TEXT,
    status          TEXT NOT NULL,
    entry_ts        REAL,
    close_ts        REAL,
    cost_sol        REAL,
    realized_pnl_sol REAL,
    exit_reason     TEXT,
    exit_reason_detail TEXT,
    data            TEXT,   -- full JSON blob
    updated_at      REAL DEFAULT (unixepoch('now'))
);

CREATE TABLE IF NOT EXISTS trade_events (
    event_id        TEXT PRIMARY KEY,
    mint            TEXT NOT NULL,
    event_type      TEXT NOT NULL,
    ts              REAL NOT NULL,
    position_id     TEXT,
    strategy_id     TEXT,
    strategy_name   TEXT,
    ledger_type     TEXT,
    pnl_sol         REAL,
    pnl_pct         REAL,
    data            TEXT    -- full JSON blob
);

CREATE TABLE IF NOT EXISTS strategy_definitions (
    definition_id   TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    version         INTEGER NOT NULL,
    updated_ts      REAL NOT NULL,
    data            TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS strategy_instances (
    strategy_id         TEXT PRIMARY KEY,
    definition_id       TEXT NOT NULL,
    name                TEXT NOT NULL,
    mode                TEXT NOT NULL,
    status              TEXT NOT NULL,
    reserved_budget_sol REAL NOT NULL,
    updated_ts          REAL NOT NULL,
    created_ts          REAL NOT NULL,
    data                TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS strategy_stats_snapshots (
    snapshot_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_id      TEXT NOT NULL,
    ts               REAL NOT NULL,
    realized_pnl_sol REAL,
    unrealized_pnl_sol REAL,
    open_positions   INTEGER,
    data             TEXT
);

CREATE INDEX IF NOT EXISTS idx_events_mint   ON trade_events(mint);
CREATE INDEX IF NOT EXISTS idx_events_type   ON trade_events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_ts     ON trade_events(ts);
CREATE INDEX IF NOT EXISTS idx_positions_mint ON positions(mint);
CREATE INDEX IF NOT EXISTS idx_positions_strategy ON positions(strategy_id);
CREATE INDEX IF NOT EXISTS idx_events_strategy ON trade_events(strategy_id);
"""


class Database:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self._conn = await aiosqlite.connect(str(self.db_path))
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(DB_SCHEMA)
        await self._ensure_columns()
        await self._conn.commit()
        logger.info(f"Database connected: {self.db_path}")

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database not connected — call connect() first")
        return self._conn

    async def execute(self, sql: str, params: tuple = ()) -> None:
        await self.conn.execute(sql, params)
        await self.conn.commit()

    async def fetchone(self, sql: str, params: tuple = ()) -> dict | None:
        async with self.conn.execute(sql, params) as cursor:
            row = await cursor.fetchone()
            if row is None:
                return None
            return dict(row)

    async def fetchall(self, sql: str, params: tuple = ()) -> list[dict]:
        async with self.conn.execute(sql, params) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    def _to_json(self, obj: Any) -> str:
        return json.dumps(obj, default=str)

    async def _ensure_columns(self) -> None:
        async def add_column_if_missing(table: str, column: str, ddl: str) -> None:
            columns = await self.fetchall(f"PRAGMA table_info({table})")
            if not any(col["name"] == column for col in columns):
                await self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")

        await add_column_if_missing("positions", "strategy_id", "TEXT")
        await add_column_if_missing("positions", "strategy_name", "TEXT")
        await add_column_if_missing("positions", "ledger_type", "TEXT")
        await add_column_if_missing("positions", "exit_reason_detail", "TEXT")
        await add_column_if_missing("trade_events", "strategy_id", "TEXT")
        await add_column_if_missing("trade_events", "strategy_name", "TEXT")
        await add_column_if_missing("trade_events", "ledger_type", "TEXT")
