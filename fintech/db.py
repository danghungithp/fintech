"""SQLite storage layer: schema, generic helpers and domain stores."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Iterable, Iterator, Optional

from .config import DB_PATH, DEFAULT_SETTINGS

_SCHEMA = """
CREATE TABLE IF NOT EXISTS symbols (
    symbol            TEXT PRIMARY KEY,
    exchange          TEXT,
    type              TEXT,
    organ_name        TEXT,
    organ_short_name  TEXT,
    updated_at        TEXT
);

CREATE TABLE IF NOT EXISTS ohlcv (
    symbol   TEXT NOT NULL,
    date     TEXT NOT NULL,
    open     REAL, high REAL, low REAL, close REAL, volume REAL,
    PRIMARY KEY (symbol, date)
);
CREATE INDEX IF NOT EXISTS idx_ohlcv_symbol ON ohlcv(symbol, date);

CREATE TABLE IF NOT EXISTS fundamentals (
    symbol         TEXT PRIMARY KEY,
    div_ps_ttm     REAL,
    market_cap     REAL,
    rating         TEXT,
    target_price   REAL,
    sector         TEXT,
    extra          TEXT,
    updated_at     TEXT
);

CREATE TABLE IF NOT EXISTS dividend_events (
    symbol   TEXT NOT NULL,
    ex_date  TEXT NOT NULL,
    amount   REAL,
    title    TEXT,
    PRIMARY KEY (symbol, ex_date)
);

CREATE TABLE IF NOT EXISTS analyses (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol       TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    price        REAL,
    signal       TEXT,
    score        REAL,
    buy_zone_low REAL, buy_zone_high REAL,
    stop_loss    REAL, target1 REAL, target2 REAL,
    payload      TEXT
);
CREATE INDEX IF NOT EXISTS idx_analyses_symbol ON analyses(symbol, created_at);

CREATE TABLE IF NOT EXISTS screen_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  TEXT NOT NULL,
    finished_at TEXT,
    status      TEXT NOT NULL,
    universe    TEXT,
    criteria    TEXT,
    total       INTEGER DEFAULT 0,
    processed   INTEGER DEFAULT 0,
    failed      INTEGER DEFAULT 0,
    error       TEXT
);

CREATE TABLE IF NOT EXISTS screen_results (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id         INTEGER NOT NULL,
    symbol         TEXT NOT NULL,
    signal         TEXT,
    score          REAL,
    price          REAL,
    change_pct     REAL,
    dividend_yield REAL,
    rsi            REAL,
    avg_volume     REAL,
    buy_zone_low   REAL, buy_zone_high REAL,
    stop_loss      REAL, target1 REAL,
    risk_reward    REAL,
    extra          TEXT
);
CREATE INDEX IF NOT EXISTS idx_screen_results_run ON screen_results(run_id);

CREATE TABLE IF NOT EXISTS positions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol      TEXT NOT NULL,
    quantity    INTEGER NOT NULL,
    avg_cost    REAL NOT NULL,
    buy_date    TEXT,
    stop_loss   REAL,
    take_profit REAL,
    note        TEXT,
    status      TEXT DEFAULT 'OPEN',
    created_at  TEXT, updated_at TEXT
);

CREATE TABLE IF NOT EXISTS watchlist (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol       TEXT UNIQUE NOT NULL,
    note         TEXT,
    target_price REAL,
    created_at   TEXT
);

CREATE TABLE IF NOT EXISTS alerts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol       TEXT NOT NULL,
    type         TEXT NOT NULL,
    severity     TEXT NOT NULL,
    message      TEXT,
    price        REAL,
    day          TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    acknowledged INTEGER DEFAULT 0,
    UNIQUE(symbol, type, day)
);
CREATE INDEX IF NOT EXISTS idx_alerts_day ON alerts(day, acknowledged);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS cache_stamps (
    symbol     TEXT PRIMARY KEY,
    updated_at TEXT
);
"""


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    return con


@contextmanager
def get_db() -> Iterator[sqlite3.Connection]:
    con = _connect()
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def init_db() -> None:
    with get_db() as con:
        con.executescript(_SCHEMA)
    for key, value in DEFAULT_SETTINGS.items():
        if get_setting(key) is None:
            set_setting(key, value)


def query(sql: str, args: Iterable = ()) -> list[dict]:
    with get_db() as con:
        rows = con.execute(sql, tuple(args)).fetchall()
    return [dict(row) for row in rows]


def query_one(sql: str, args: Iterable = ()) -> Optional[dict]:
    rows = query(sql, args)
    return rows[0] if rows else None


def execute(sql: str, args: Iterable = ()) -> int:
    with get_db() as con:
        cur = con.execute(sql, tuple(args))
        return cur.lastrowid or 0


def executemany(sql: str, rows: list[tuple]) -> None:
    with get_db() as con:
        con.executemany(sql, rows)


# ---------------------------------------------------------------- settings

def get_setting(key: str, default: Any = None) -> Any:
    row = query_one("SELECT value FROM settings WHERE key = ?", (key,))
    if row is None:
        if default is not None:
            return default
        return DEFAULT_SETTINGS.get(key)
    raw = row["value"]
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return raw


def set_setting(key: str, value: Any) -> None:
    execute(
        "INSERT INTO settings(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, json.dumps(value)),
    )


def get_settings() -> dict:
    merged = dict(DEFAULT_SETTINGS)
    for row in query("SELECT key, value FROM settings"):
        try:
            merged[row["key"]] = json.loads(row["value"])
        except (TypeError, ValueError):
            merged[row["key"]] = row["value"]
    return merged


# ---------------------------------------------------------------- symbols

def save_symbols(records: list[dict]) -> int:
    rows = [
        (
            r.get("symbol"),
            r.get("exchange"),
            r.get("type"),
            r.get("organ_name"),
            r.get("organ_short_name"),
            now_str(),
        )
        for r in records
        if r.get("symbol")
    ]
    if not rows:
        return 0
    executemany(
        "INSERT INTO symbols(symbol, exchange, type, organ_name, organ_short_name, updated_at) "
        "VALUES(?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(symbol) DO UPDATE SET exchange = excluded.exchange, type = excluded.type, "
        "organ_name = excluded.organ_name, organ_short_name = excluded.organ_short_name, "
        "updated_at = excluded.updated_at",
        rows,
    )
    return len(rows)


def symbol_meta(symbol: str) -> Optional[dict]:
    return query_one("SELECT * FROM symbols WHERE symbol = ?", (symbol.upper(),))


def search_symbols(term: str = "", limit: int = 20) -> list[dict]:
    term = (term or "").strip().upper()
    exchange_rank = (
        "CASE exchange WHEN 'HOSE' THEN 0 WHEN 'HNX' THEN 1 WHEN 'UPCOM' THEN 2 ELSE 3 END"
    )
    if term:
        like = f"%{term}%"
        return query(
            "SELECT symbol, exchange, organ_short_name, organ_name FROM symbols "
            "WHERE symbol LIKE ? OR UPPER(organ_short_name) LIKE ? OR UPPER(organ_name) LIKE ? "
            "ORDER BY CASE WHEN symbol = ? THEN 0 WHEN symbol LIKE ? THEN 1 ELSE 2 END, "
            f"CASE WHEN type = 'STOCK' THEN 0 ELSE 1 END, {exchange_rank}, symbol "
            "LIMIT ?",
            (like, like, like, term, f"{term}%", limit),
        )
    return query(
        "SELECT symbol, exchange, organ_short_name, organ_name FROM symbols "
        "WHERE type = 'STOCK' OR type IS NULL OR type = '' "
        f"ORDER BY {exchange_rank}, symbol LIMIT ?",
        (limit,),
    )


# ---------------------------------------------------------------- candles

def save_candles(symbol: str, candles: list[dict]) -> None:
    rows = [
        (
            symbol.upper(),
            c["t"],
            float(c["o"]),
            float(c["h"]),
            float(c["l"]),
            float(c["c"]),
            float(c.get("v") or 0),
        )
        for c in candles
        if c.get("t")
    ]
    if not rows:
        return
    executemany(
        "INSERT INTO ohlcv(symbol, date, open, high, low, close, volume) "
        "VALUES(?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(symbol, date) DO UPDATE SET open = excluded.open, high = excluded.high, "
        "low = excluded.low, close = excluded.close, volume = excluded.volume",
        rows,
    )


def load_candles(symbol: str, limit: int = 400) -> list[dict]:
    rows = query(
        "SELECT date, open, high, low, close, volume FROM ohlcv "
        "WHERE symbol = ? ORDER BY date DESC LIMIT ?",
        (symbol.upper(), limit),
    )
    rows.reverse()
    return [
        {
            "t": r["date"],
            "o": r["open"],
            "h": r["high"],
            "l": r["low"],
            "c": r["close"],
            "v": r["volume"] or 0,
        }
        for r in rows
    ]


def candle_stats(symbol: str) -> Optional[dict]:
    return query_one(
        "SELECT MAX(date) AS last_date, COUNT(*) AS n FROM ohlcv WHERE symbol = ?",
        (symbol.upper(),),
    )


def save_cache_stamp(symbol: str) -> None:
    execute(
        "INSERT INTO cache_stamps(symbol, updated_at) VALUES(?, ?) "
        "ON CONFLICT(symbol) DO UPDATE SET updated_at = excluded.updated_at",
        (symbol.upper(), now_str()),
    )


def load_cache_stamp(symbol: str) -> Optional[str]:
    row = query_one("SELECT updated_at FROM cache_stamps WHERE symbol = ?", (symbol.upper(),))
    return row["updated_at"] if row else None


# ------------------------------------------------------------ fundamentals

def save_fundamentals(symbol: str, data: dict) -> None:
    execute(
        "INSERT INTO fundamentals(symbol, div_ps_ttm, market_cap, rating, target_price, sector, extra, updated_at) "
        "VALUES(?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(symbol) DO UPDATE SET div_ps_ttm = excluded.div_ps_ttm, "
        "market_cap = excluded.market_cap, rating = excluded.rating, "
        "target_price = excluded.target_price, sector = excluded.sector, "
        "extra = excluded.extra, updated_at = excluded.updated_at",
        (
            symbol.upper(),
            data.get("div_ps_ttm"),
            data.get("market_cap"),
            data.get("rating"),
            data.get("target_price"),
            data.get("sector"),
            json.dumps(data.get("extra") or {}, ensure_ascii=False),
            now_str(),
        ),
    )


def load_fundamentals(symbol: str) -> Optional[dict]:
    row = query_one("SELECT * FROM fundamentals WHERE symbol = ?", (symbol.upper(),))
    if not row:
        return None
    try:
        row["extra"] = json.loads(row.get("extra") or "{}")
    except (TypeError, ValueError):
        row["extra"] = {}
    return row


def save_dividend_events(symbol: str, events: list[dict]) -> None:
    rows = [
        (symbol.upper(), e["ex_date"], e.get("amount"), e.get("title"))
        for e in events
        if e.get("ex_date")
    ]
    if not rows:
        return
    executemany(
        "INSERT INTO dividend_events(symbol, ex_date, amount, title) VALUES(?, ?, ?, ?) "
        "ON CONFLICT(symbol, ex_date) DO UPDATE SET amount = excluded.amount, title = excluded.title",
        rows,
    )


def load_dividend_events(symbol: str, limit: int = 12) -> list[dict]:
    return query(
        "SELECT ex_date, amount, title FROM dividend_events WHERE symbol = ? "
        "ORDER BY ex_date DESC LIMIT ?",
        (symbol.upper(), limit),
    )


# -------------------------------------------------------------- analyses

def save_analysis(payload: dict) -> None:
    levels = payload.get("levels") or {}
    signal = payload.get("signal") or {}
    buy_zone = levels.get("buy_zone") or [None, None]
    sell_points = levels.get("sell_points") or []
    execute(
        "INSERT INTO analyses(symbol, created_at, price, signal, score, buy_zone_low, buy_zone_high, "
        "stop_loss, target1, target2, payload) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            payload.get("symbol"),
            now_str(),
            payload.get("price"),
            signal.get("code"),
            signal.get("score"),
            buy_zone[0] if len(buy_zone) > 0 else None,
            buy_zone[1] if len(buy_zone) > 1 else None,
            levels.get("stop_loss"),
            (sell_points[0] or {}).get("price") if sell_points else None,
            (sell_points[1] or {}).get("price") if len(sell_points) > 1 else None,
            json.dumps(payload, ensure_ascii=False),
        ),
    )


def recent_analyses(limit: int = 20) -> list[dict]:
    return query(
        "SELECT id, symbol, created_at, price, signal, score, buy_zone_low, buy_zone_high, "
        "stop_loss, target1 FROM analyses ORDER BY id DESC LIMIT ?",
        (limit,),
    )


def last_analysis(symbol: str) -> Optional[dict]:
    return query_one(
        "SELECT * FROM analyses WHERE symbol = ? ORDER BY id DESC LIMIT 1",
        (symbol.upper(),),
    )
