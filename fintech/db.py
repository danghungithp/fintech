"""InfluxDB (Cloud Serverless) storage layer: measurements + domain stores.

The former SQLite schema is mapped onto InfluxDB 3 measurements. Cloud
Serverless rejects all DML (UPDATE / DELETE / INSERT INTO) and enforces a
30-day retention on the bucket, so this layer follows two rules:

* Writes are append-only. The newest point per logical key (by point time) is
  the current version of a row; read paths dedupe in Python and ``None``
  defaults cover fields a version does not carry.
* Points are stamped with ingest time, never with historical dates — points
  older than the retention window would be dropped on write. Dates that carry
  meaning (candle session, ex-dividend date) are stored as plain fields.

Deletes and acknowledgements append a new version for the same key (tombstone
flags) instead of mutating history. ``init_db()`` "touches" active rows
(settings, positions, watchlist, unacknowledged alerts, recent analyses) on
every process start, refreshing their retention clock so irreplaceable user
data survives indefinitely as long as the app is opened at least once per
30 days. Cache-like data (candles, fundamentals, symbols, screen logs) is
refetched or recomputed, so it is intentionally left to age out.
"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from influxdb_client_3 import Point

from . import influx
from .config import DEFAULT_SETTINGS

_lock = threading.Lock()
_initialized = False

# Column names that exist only inside InfluxDB (never part of the public rows).
_INTERNAL = ("time",)


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


# ------------------------------------------------------------------ helpers

def _new_id() -> int:
    """Microsecond epoch id — unique per process, fits in a JS safe integer."""
    return time.time_ns() // 1000


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _stamp(index: int = 0) -> datetime:
    """Ingest timestamp for one point of a batch.

    Points sharing a measurement, tag set and timestamp overwrite each other,
    so points written within the same batch (candles of one symbol, events of
    one symbol, results of one run) get microsecond offsets to stay distinct.
    """
    return _utcnow() + timedelta(microseconds=index)


def _point(measure: str, tags: dict, fields: dict, ts: Optional[datetime] = None) -> Point:
    point = Point(measure)
    for key, value in tags.items():
        point = point.tag(key, str(value))
    for key, value in fields.items():
        if value is None:
            continue
        point = point.field(key, value)
    return point.time(ts or _utcnow())


def _write(points: list) -> None:
    influx.write_points(points)


def _fetch(statement: str) -> list[dict]:
    return influx.fetch(statement)


def _sql_str(value: Any) -> str:
    return influx.sql_str(value)


def _latest(rows: list[dict], key) -> list[dict]:
    """Keep only the newest point (by ``time``) for each logical key."""
    best: dict = {}
    for row in rows:
        row_key = key(row)
        current = best.get(row_key)
        if current is None or row["time"] > current["time"]:
            best[row_key] = row
    return list(best.values())


def _public(row: dict, drop: tuple = ()) -> dict:
    return {k: v for k, v in row.items() if k not in _INTERNAL and k not in drop}


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _json_load(raw: Any, fallback: Any) -> Any:
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return fallback


def _drop_keys(row: dict, keys: tuple) -> dict:
    return {k: v for k, v in row.items() if k not in keys}


# A field is only present in the table schema once some row wrote it, so public
# rows are rebuilt with the full expected key set (None for absent values).

_POSITION_KEYS = (
    "symbol", "quantity", "avg_cost", "buy_date", "stop_loss", "take_profit",
    "note", "status", "created_at", "updated_at",
)
_WATCH_KEYS = ("symbol", "note", "target_price", "created_at")
_RUN_KEYS = (
    "created_at", "finished_at", "status", "universe", "criteria",
    "total", "processed", "failed", "error",
)
_RESULT_KEYS = (
    "symbol", "signal", "score", "price", "change_pct", "dividend_yield",
    "rsi", "avg_volume", "buy_zone_low", "buy_zone_high", "stop_loss",
    "target1", "risk_reward", "extra",
)


def _position_row(row: dict) -> dict:
    out = {key: row.get(key) for key in _POSITION_KEYS}
    out["id"] = _as_int(row.get("id"))
    return out


def _watch_row(row: dict) -> dict:
    out = {key: row.get(key) for key in _WATCH_KEYS}
    out["id"] = _as_int(row.get("id"))
    return out


def _run_row(row: dict) -> dict:
    out = {key: row.get(key) for key in _RUN_KEYS}
    out["id"] = _as_int(row.get("id"))
    return out


def _result_row(row: dict) -> dict:
    out = {key: row.get(key) for key in _RESULT_KEYS}
    out["run_id"] = _as_int(row.get("run_id"))
    return out


# ------------------------------------------------------------- init / touch

def init_db() -> None:
    """Prepare storage. Defaults are merged at read time, so the only work is
    refreshing the retention clock of active user data (best-effort)."""
    global _initialized
    with _lock:
        if _initialized:
            return
        _initialized = True
    try:
        _touch_active_rows()
    except Exception:  # noqa: BLE001 - storage must not block app startup
        pass


def _touch_active_rows() -> None:
    """Re-write active rows with a fresh ingest timestamp.

    Cloud Serverless keeps points for 30 days; touching keeps positions,
    watchlist, settings, unacknowledged alerts and recent analyses alive while
    the app is in use, without duplicating any logical row.
    """
    now = _utcnow()
    points: list = []

    for row in _latest(_fetch("SELECT * FROM settings"), lambda r: r.get("key")):
        points.append(_point("settings", {"key": row.get("key")}, {"value": row.get("value")}, ts=now))

    for row in _latest(_fetch("SELECT * FROM positions"), lambda r: r.get("id")):
        if row.get("deleted"):
            continue
        fields = _drop_keys(row, ("time", "id"))
        points.append(_point("positions", {"id": row.get("id")}, fields, ts=now))

    for row in _latest(_fetch("SELECT * FROM watchlist"), lambda r: r.get("symbol")):
        if row.get("deleted"):
            continue
        fields = _drop_keys(row, ("time", "id", "symbol"))
        points.append(_point("watchlist", {"id": row.get("id"), "symbol": row.get("symbol")}, fields, ts=now))

    for row in _latest(_fetch("SELECT * FROM alerts"), lambda r: (r.get("symbol"), r.get("alert_type"), r.get("day"))):
        if _as_int(row.get("acknowledged")):
            continue
        fields = _drop_keys(row, ("time", "id", "symbol", "alert_type", "day"))
        tags = {key: row.get(key) for key in ("id", "symbol", "alert_type", "day")}
        points.append(_point("alerts", tags, fields, ts=now))

    for row in _fetch("SELECT * FROM analyses ORDER BY time DESC LIMIT 10"):
        fields = _drop_keys(row, ("time", "id"))
        points.append(_point("analyses", {"id": row.get("id")}, fields, ts=now))

    for row in _latest(_fetch("SELECT * FROM users"), lambda r: r.get("id")):
        if row.get("deleted"):
            continue
        fields = _drop_keys(row, ("time", "id"))
        points.append(_point("users", {"id": row.get("id")}, fields, ts=now))

    for row in _latest(_fetch("SELECT * FROM trades"), lambda r: r.get("id")):
        if row.get("deleted"):
            continue
        fields = _drop_keys(row, ("time", "id"))
        points.append(_point("trades", {"id": row.get("id")}, fields, ts=now))

    _write(points)


# ---------------------------------------------------------------- settings

def get_setting(key: str, default: Any = None) -> Any:
    rows = _fetch("SELECT * FROM settings")
    latest = {r.get("key"): r for r in _latest(rows, lambda r: r.get("key"))}
    row = latest.get(key)
    if row is None:
        if default is not None:
            return default
        return DEFAULT_SETTINGS.get(key)
    return _json_load(row.get("value"), row.get("value"))


def set_setting(key: str, value: Any) -> None:
    _write([_point("settings", {"key": key}, {"value": json.dumps(value)})])


def get_settings() -> dict:
    merged = dict(DEFAULT_SETTINGS)
    rows = _fetch("SELECT * FROM settings")
    for row in _latest(rows, lambda r: r.get("key")):
        merged[row.get("key")] = _json_load(row.get("value"), row.get("value"))
    return merged


# ----------------------------------------------------------------- symbols
# The Vietcap listing is refreshed as a whole generation: every refresh writes
# all rows under a new ``gen`` tag, so the newest generation is the listing.

def _symbols_gen() -> Optional[str]:
    rows = _fetch("SELECT MAX(gen) AS g FROM symbols")
    value = rows[0].get("g") if rows else None
    return str(value) if value else None


def _current_symbols() -> list[dict]:
    gen = _symbols_gen()
    if not gen:
        return []
    return _fetch(f"SELECT * FROM symbols WHERE gen = {_sql_str(gen)}")


def save_symbols(records: list[dict]) -> int:
    rows = [r for r in records if r.get("symbol")]
    if not rows:
        return 0
    gen = str(_new_id())
    now = _utcnow()
    updated_at = now_str()
    points = [
        _point(
            "symbols",
            {"gen": gen, "symbol": r["symbol"]},
            {
                "exchange": r.get("exchange"),
                "type": r.get("type"),
                "organ_name": r.get("organ_name"),
                "organ_short_name": r.get("organ_short_name"),
                "updated_at": updated_at,
            },
            ts=now,
        )
        for r in rows
    ]
    _write(points)
    return len(points)


def symbol_stats() -> Optional[dict]:
    """COUNT + newest updated_at of the current listing generation."""
    gen = _symbols_gen()
    if not gen:
        return {"n": 0, "updated": None}
    rows = _fetch(
        f"SELECT COUNT(*) AS n, MAX(updated_at) AS updated FROM symbols WHERE gen = {_sql_str(gen)}"
    )
    return rows[0] if rows else {"n": 0, "updated": None}


def symbol_meta(symbol: str) -> Optional[dict]:
    gen = _symbols_gen()
    if not gen:
        return None
    rows = _fetch(
        f"SELECT * FROM symbols WHERE gen = {_sql_str(gen)} AND symbol = {_sql_str(symbol.upper())}"
        " ORDER BY time DESC LIMIT 1"
    )
    if not rows:
        return None
    return _public(rows[0], drop=("gen",))


_EXCHANGE_RANK = {"HOSE": 0, "HNX": 1, "UPCOM": 2}


def _exchange_rank(exchange: Any) -> int:
    return _EXCHANGE_RANK.get(exchange or "", 3)


def search_symbols(term: str = "", limit: int = 20) -> list[dict]:
    rows = _current_symbols()
    if not rows:
        return []
    term = (term or "").strip().upper()
    if term:
        def matches(row: dict) -> bool:
            return (
                term in (row.get("symbol") or "")
                or term in (row.get("organ_short_name") or "").upper()
                or term in (row.get("organ_name") or "").upper()
            )

        def tier(row: dict) -> int:
            symbol = row.get("symbol") or ""
            if symbol == term:
                return 0
            if symbol.startswith(term):
                return 1
            return 2

        picked = [r for r in rows if matches(r)]
        picked.sort(key=lambda r: (
            tier(r),
            0 if r.get("type") == "STOCK" else 1,
            _exchange_rank(r.get("exchange")),
            r.get("symbol") or "",
        ))
    else:
        picked = [r for r in rows if (r.get("type") or "") in ("STOCK", "")]
        picked.sort(key=lambda r: (_exchange_rank(r.get("exchange")), r.get("symbol") or ""))
    return [
        {
            "symbol": r.get("symbol"),
            "exchange": r.get("exchange"),
            "organ_short_name": r.get("organ_short_name"),
            "organ_name": r.get("organ_name"),
        }
        for r in picked[:limit]
    ]


def symbols_by_exchange(exchange: str) -> list[str]:
    rows = _current_symbols()
    picked = [
        r for r in rows
        if (r.get("exchange") or "") == exchange and (r.get("type") == "STOCK" or r.get("type") == "")
    ]
    picked.sort(key=lambda r: r.get("symbol") or "")
    return [r["symbol"] for r in picked]


# ----------------------------------------------------------------- candles
# Points are stamped with ingest time (history beyond the retention window
# would otherwise be dropped); the session date is the ``trade_date`` field and
# is the dedupe key. Unchanged sessions are not rewritten, which keeps the
# measurement roughly bounded by the history window.

def save_candles(symbol: str, candles: list[dict]) -> None:
    symbol = symbol.upper()
    rows = [c for c in candles if c.get("t")]
    if not rows:
        return
    existing_rows = _fetch(f"SELECT * FROM candles WHERE symbol = {_sql_str(symbol)}")
    existing = {r.get("trade_date"): r for r in _latest(existing_rows, lambda r: r.get("trade_date"))}
    keys = ("open", "high", "low", "close", "volume")
    points = []
    for index, c in enumerate(rows):
        values = (
            float(c["o"]),
            float(c["h"]),
            float(c["l"]),
            float(c["c"]),
            float(c.get("v") or 0),
        )
        current = existing.get(c["t"])
        if current is not None and all(
            (current.get(key) or 0) == value for key, value in zip(keys, values)
        ):
            continue
        fields = {"trade_date": c["t"]}
        fields.update(dict(zip(keys, values)))
        points.append(_point("candles", {"symbol": symbol}, fields, ts=_stamp(index)))
    _write(points)


def load_candles(symbol: str, limit: int = 400) -> list[dict]:
    symbol = symbol.upper()
    rows = _fetch(f"SELECT * FROM candles WHERE symbol = {_sql_str(symbol)}")
    rows = _latest([r for r in rows if r.get("trade_date")], lambda r: r.get("trade_date"))
    rows.sort(key=lambda r: r.get("trade_date"), reverse=True)
    rows = rows[:limit]
    rows.reverse()
    return [
        {
            "t": r.get("trade_date"),
            "o": r.get("open"),
            "h": r.get("high"),
            "l": r.get("low"),
            "c": r.get("close"),
            "v": r.get("volume") or 0,
        }
        for r in rows
    ]


def candle_stats(symbol: str) -> Optional[dict]:
    symbol = symbol.upper()
    rows = _fetch(f"SELECT * FROM candles WHERE symbol = {_sql_str(symbol)}")
    rows = _latest([r for r in rows if r.get("trade_date")], lambda r: r.get("trade_date"))
    if not rows:
        return {"last_date": None, "n": 0}
    return {"last_date": max(r["trade_date"] for r in rows), "n": len(rows)}


def save_cache_stamp(symbol: str) -> None:
    _write([_point("cache_stamps", {"symbol": symbol.upper()}, {"updated_at": now_str()})])


def load_cache_stamp(symbol: str) -> Optional[str]:
    rows = _fetch(
        f"SELECT * FROM cache_stamps WHERE symbol = {_sql_str(symbol.upper())} ORDER BY time DESC LIMIT 1"
    )
    return rows[0].get("updated_at") if rows else None


# ------------------------------------------------------------ fundamentals

def save_fundamentals(symbol: str, data: dict) -> None:
    _write([_point(
        "fundamentals",
        {"symbol": symbol.upper()},
        {
            "div_ps_ttm": data.get("div_ps_ttm"),
            "market_cap": data.get("market_cap"),
            "rating": data.get("rating"),
            "target_price": data.get("target_price"),
            "sector": data.get("sector"),
            "extra": json.dumps(data.get("extra") or {}, ensure_ascii=False),
            "updated_at": now_str(),
        },
    )])


def load_fundamentals(symbol: str) -> Optional[dict]:
    rows = _fetch(
        f"SELECT * FROM fundamentals WHERE symbol = {_sql_str(symbol.upper())} ORDER BY time DESC LIMIT 1"
    )
    if not rows:
        return None
    row = _public(rows[0])
    row["extra"] = _json_load(row.get("extra"), {})
    return row


def save_dividend_events(symbol: str, events: list[dict]) -> None:
    rows = [e for e in events if e.get("ex_date")]
    if not rows:
        return
    symbol = symbol.upper()
    points = [
        _point(
            "dividend_events",
            {"symbol": symbol},
            {"ex_date": e["ex_date"], "amount": e.get("amount"), "title": e.get("title")},
            ts=_stamp(index),
        )
        for index, e in enumerate(rows)
    ]
    _write(points)


def load_dividend_events(symbol: str, limit: int = 12) -> list[dict]:
    rows = _fetch(f"SELECT * FROM dividend_events WHERE symbol = {_sql_str(symbol.upper())}")
    rows = _latest([r for r in rows if r.get("ex_date")], lambda r: r.get("ex_date"))
    rows.sort(key=lambda r: r.get("ex_date"), reverse=True)
    return [
        {"ex_date": r.get("ex_date"), "amount": r.get("amount"), "title": r.get("title")}
        for r in rows[:limit]
    ]


# ---------------------------------------------------------------- analyses

def save_analysis(payload: dict) -> None:
    levels = payload.get("levels") or {}
    signal = payload.get("signal") or {}
    buy_zone = levels.get("buy_zone") or [None, None]
    sell_points = levels.get("sell_points") or []
    _write([_point(
        "analyses",
        {"id": str(_new_id())},
        {
            "symbol": payload.get("symbol"),
            "created_at": now_str(),
            "price": payload.get("price"),
            "signal": signal.get("code"),
            "score": signal.get("score"),
            "buy_zone_low": buy_zone[0] if len(buy_zone) > 0 else None,
            "buy_zone_high": buy_zone[1] if len(buy_zone) > 1 else None,
            "stop_loss": levels.get("stop_loss"),
            "target1": (sell_points[0] or {}).get("price") if sell_points else None,
            "target2": (sell_points[1] or {}).get("price") if len(sell_points) > 1 else None,
            "payload": json.dumps(payload, ensure_ascii=False),
        },
    )])


def recent_analyses(limit: int = 20) -> list[dict]:
    rows = _fetch(f"SELECT * FROM analyses ORDER BY time DESC LIMIT {int(limit)}")
    return [
        {
            "id": _as_int(r.get("id")),
            "symbol": r.get("symbol"),
            "created_at": r.get("created_at"),
            "price": r.get("price"),
            "signal": r.get("signal"),
            "score": r.get("score"),
            "buy_zone_low": r.get("buy_zone_low"),
            "buy_zone_high": r.get("buy_zone_high"),
            "stop_loss": r.get("stop_loss"),
            "target1": r.get("target1"),
        }
        for r in rows
    ]


def last_analysis(symbol: str) -> Optional[dict]:
    rows = _fetch(
        f"SELECT * FROM analyses WHERE symbol = {_sql_str(symbol.upper())} ORDER BY time DESC LIMIT 1"
    )
    if not rows:
        return None
    row = _public(rows[0])
    row["id"] = _as_int(row.get("id"))
    return row


# ------------------------------------------------------------- screen runs

def screen_run_create(universe_json: str, criteria_json: str) -> int:
    run_id = _new_id()
    _write([_point(
        "screen_runs",
        {"id": str(run_id)},
        {
            "created_at": now_str(),
            "status": "RUNNING",
            "universe": universe_json,
            "criteria": criteria_json,
            "total": 0,
            "processed": 0,
            "failed": 0,
        },
    )])
    return run_id


def screen_run_latest(run_id: int) -> Optional[dict]:
    rows = _fetch(
        f"SELECT * FROM screen_runs WHERE id = {_sql_str(_as_int(run_id))} ORDER BY time DESC LIMIT 1"
    )
    if not rows:
        return None
    return _run_row(rows[0])


def screen_run_update(run_id: int, updates: dict) -> None:
    """Append a new full-state version of a run (field merge over latest)."""
    row = screen_run_latest(run_id)
    if row is None:
        return
    merged = {**row, **updates}
    merged.pop("id", None)
    _write([_point("screen_runs", {"id": str(_as_int(run_id))}, merged)])


def screen_run_latest_running() -> Optional[dict]:
    # Older versions of a finished run still match ``status = 'RUNNING'``, so
    # candidates are collected first and their full version history is then
    # deduped before checking which runs are still running.
    candidates = _fetch("SELECT id FROM screen_runs WHERE status = 'RUNNING'")
    ids = {_as_int(r.get("id")) for r in candidates if r.get("id")}
    if not ids:
        return None
    id_list = ", ".join(_sql_str(i) for i in sorted(ids))
    rows = _fetch(f"SELECT * FROM screen_runs WHERE id IN ({id_list})")
    running = [r for r in _latest(rows, lambda r: r.get("id")) if r.get("status") == "RUNNING"]
    if not running:
        return None
    row = max(running, key=lambda r: _as_int(r.get("id")))
    return {"id": _as_int(row.get("id")), "created_at": row.get("created_at")}


def screen_run_ids(limit: int = 12) -> list[int]:
    rows = _fetch(
        f"SELECT id, MAX(time) AS t FROM screen_runs GROUP BY id ORDER BY t DESC LIMIT {int(limit)}"
    )
    return [_as_int(r.get("id")) for r in rows if r.get("id")]


def screen_runs_latest(run_ids: list[int]) -> dict:
    ids = [_as_int(i) for i in run_ids]
    if not ids:
        return {}
    id_list = ", ".join(_sql_str(i) for i in ids)
    rows = _fetch(f"SELECT * FROM screen_runs WHERE id IN ({id_list})")
    out: dict = {}
    for row in _latest(rows, lambda r: r.get("id")):
        public = _run_row(row)
        out[public["id"]] = public
    return out


# ---------------------------------------------------------- screen results

def screen_results_save(batch: list[dict]) -> None:
    if not batch:
        return
    points = [
        _point("screen_results", {"run_id": str(_as_int(row.get("run_id")))},
               _drop_keys(row, ("run_id",)), ts=_stamp(index))
        for index, row in enumerate(batch)
    ]
    _write(points)


def screen_results_for_run(run_id: int) -> list[dict]:
    rows = _fetch(f"SELECT * FROM screen_results WHERE run_id = {_sql_str(_as_int(run_id))}")
    out = [_result_row(row) for row in rows]

    def sort_key(row: dict):
        score = row.get("score")
        dividend = row.get("dividend_yield")
        return (score is None, -(score or 0.0), dividend is None, -(dividend or 0.0))

    out.sort(key=sort_key)
    return out


def screen_results_counts(run_ids: list[int]) -> dict:
    ids = [_as_int(i) for i in run_ids]
    if not ids:
        return {}
    id_list = ", ".join(_sql_str(i) for i in ids)
    rows = _fetch(
        f"SELECT run_id, COUNT(*) AS n FROM screen_results WHERE run_id IN ({id_list}) GROUP BY run_id"
    )
    return {_as_int(r.get("run_id")): _as_int(r.get("n")) for r in rows}


# --------------------------------------------------------------- positions

def position_create(fields: dict) -> int:
    position_id = _new_id()
    _write([_point("positions", {"id": str(position_id)}, fields)])
    return position_id


def _position_rows() -> list[dict]:
    rows = _fetch("SELECT * FROM positions")
    out = []
    for row in _latest(rows, lambda r: r.get("id")):
        if row.get("deleted"):
            continue
        out.append(_position_row(row))
    return out


def positions_open() -> list[dict]:
    rows = [r for r in _position_rows() if r.get("status") == "OPEN"]
    rows.sort(key=lambda r: r.get("id"))
    return rows


def position_latest(position_id: int) -> Optional[dict]:
    rows = _fetch(
        f"SELECT * FROM positions WHERE id = {_sql_str(_as_int(position_id))} ORDER BY time DESC LIMIT 1"
    )
    if not rows or rows[0].get("deleted"):
        return None
    return _position_row(rows[0])


def position_put(position_id: int, updates: dict) -> None:
    """Append a new version merging ``updates`` over the latest row."""
    row = position_latest(position_id)
    if row is None:
        return
    merged = {**row, **updates, "updated_at": now_str()}
    merged.pop("id", None)
    _write([_point("positions", {"id": str(_as_int(position_id))}, merged)])


def position_delete(position_id: int) -> None:
    row = position_latest(position_id)
    if row is None:
        return
    merged = {**row, "deleted": True}
    merged.pop("id", None)
    _write([_point("positions", {"id": str(_as_int(position_id))}, merged)])


# --------------------------------------------------------------- watchlist

def _watch_latest_by_symbol() -> dict:
    rows = _fetch("SELECT * FROM watchlist")
    return {r.get("symbol"): r for r in _latest(rows, lambda r: r.get("symbol"))}


def watchlist_all() -> list[dict]:
    out = []
    for row in _watch_latest_by_symbol().values():
        if row.get("deleted"):
            continue
        out.append(_watch_row(row))
    out.sort(key=lambda r: r.get("id"), reverse=True)
    return out


def watch_add(symbol: str, note: Optional[str], target_price: Optional[float]) -> int:
    """Upsert by symbol: an existing entry keeps its id and created_at."""
    current = _watch_latest_by_symbol().get(symbol)
    if current is not None and not current.get("deleted"):
        watch_id = _as_int(current.get("id"))
        created_at = current.get("created_at")
    else:
        watch_id = _new_id()
        created_at = now_str()
    _write([_point(
        "watchlist",
        {"id": str(watch_id), "symbol": symbol},
        {"note": note, "target_price": target_price, "created_at": created_at},
    )])
    return watch_id


def watch_remove(watch_id: int) -> None:
    rows = _fetch(
        f"SELECT * FROM watchlist WHERE id = {_sql_str(_as_int(watch_id))} ORDER BY time DESC LIMIT 1"
    )
    if not rows or rows[0].get("deleted"):
        return
    row = rows[0]
    fields = _drop_keys(row, ("time", "id", "symbol"))
    fields["deleted"] = True
    _write([_point("watchlist", {"id": row.get("id"), "symbol": row.get("symbol")}, fields)])


# ------------------------------------------------------------------ alerts
# Key = (symbol, type, day). Re-raising the same alert refreshes message /
# severity / price / created_at while preserving id and acknowledged (the
# former ON CONFLICT semantics); acknowledging appends a new version.

def _alerts_raw() -> list[dict]:
    rows = _fetch("SELECT * FROM alerts")
    return _latest(rows, lambda r: (r.get("symbol"), r.get("alert_type"), r.get("day")))


def _alert_public(row: dict) -> dict:
    return {
        "id": _as_int(row.get("id")),
        "symbol": row.get("symbol"),
        "type": row.get("alert_type"),
        "severity": row.get("severity"),
        "message": row.get("message"),
        "price": row.get("price"),
        "day": row.get("day"),
        "created_at": row.get("created_at"),
        "acknowledged": _as_int(row.get("acknowledged")),
    }


def alert_upsert(symbol: str, alert_type: str, severity: str, message: str, price: Any) -> None:
    day = today_str()
    rows = _fetch(
        "SELECT * FROM alerts"
        f" WHERE symbol = {_sql_str(symbol)} AND alert_type = {_sql_str(alert_type)} AND day = {_sql_str(day)}"
        " ORDER BY time DESC LIMIT 1"
    )
    current = rows[0] if rows else None
    alert_id = current.get("id") if current else str(_new_id())
    acknowledged = _as_int(current.get("acknowledged")) if current else 0
    _write([_point(
        "alerts",
        {"id": alert_id, "symbol": symbol, "alert_type": alert_type, "day": day},
        {
            "severity": severity,
            "message": message,
            "price": price,
            "created_at": now_str(),
            "acknowledged": acknowledged,
        },
    )])


def alerts_list(limit: int = 100, include_ack: bool = False) -> list[dict]:
    rows = [_alert_public(r) for r in _alerts_raw()]
    if not include_ack:
        rows = [r for r in rows if not r["acknowledged"]]
    rows.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    return rows[:limit]


def alerts_count() -> int:
    return sum(1 for r in _alerts_raw() if not _as_int(r.get("acknowledged")))


def alert_ack(alert_id: int) -> None:
    rows = _fetch(
        f"SELECT * FROM alerts WHERE id = {_sql_str(_as_int(alert_id))} ORDER BY time DESC LIMIT 1"
    )
    if not rows:
        return
    row = rows[0]
    fields = _drop_keys(row, ("time", "id", "symbol", "alert_type", "day"))
    fields["acknowledged"] = 1
    tags = {key: row.get(key) for key in ("id", "symbol", "alert_type", "day")}
    _write([_point("alerts", tags, fields)])


def alert_ack_all() -> None:
    points = []
    for row in _alerts_raw():
        if _as_int(row.get("acknowledged")):
            continue
        fields = _drop_keys(row, ("time", "id", "symbol", "alert_type", "day"))
        fields["acknowledged"] = 1
        tags = {key: row.get(key) for key in ("id", "symbol", "alert_type", "day")}
        points.append(_point("alerts", tags, fields))
    _write(points)


# -------------------------------------------------------------------- users

def user_create(email: str, password_hash: str, name: str = "", role: str = "user") -> int:
    user_id = _new_id()
    _write([_point(
        "users",
        {"id": str(user_id)},
        {
            "email": (email or "").strip().lower(),
            "password_hash": password_hash,
            "name": name or "",
            "role": role or "user",
            "active": 1,
            "created_at": now_str(),
            "updated_at": now_str(),
        },
    )])
    return user_id


def user_by_email(email: str) -> Optional[dict]:
    email = (email or "").strip().lower()
    if not email:
        return None
    rows = _fetch(
        f"SELECT * FROM users WHERE email = {_sql_str(email)}"
        " ORDER BY time DESC LIMIT 1"
    )
    if not rows or rows[0].get("deleted"):
        return None
    row = _public(rows[0])
    row["id"] = _as_int(row.get("id"))
    row["active"] = _as_int(row.get("active"), 1)
    return row


def user_latest(user_id: int) -> Optional[dict]:
    rows = _fetch(
        f"SELECT * FROM users WHERE id = {_sql_str(_as_int(user_id))}"
        " ORDER BY time DESC LIMIT 1"
    )
    if not rows or rows[0].get("deleted"):
        return None
    row = _public(rows[0])
    row["id"] = _as_int(row.get("id"))
    row["active"] = _as_int(row.get("active"), 1)
    return row


def users_list() -> list[dict]:
    out = []
    for row in _latest(_fetch("SELECT * FROM users"), lambda r: r.get("id")):
        if row.get("deleted"):
            continue
        out.append({
            "id": _as_int(row.get("id")),
            "email": row.get("email"),
            "name": row.get("name"),
            "role": row.get("role") or "user",
            "active": _as_int(row.get("active"), 1),
            "created_at": row.get("created_at"),
        })
    out.sort(key=lambda r: r.get("id") or 0, reverse=True)
    return out


def user_set_active(user_id: int, active: bool) -> None:
    row = user_latest(user_id)
    if row is None:
        return
    merged = {**row, "active": 1 if active else 0, "updated_at": now_str()}
    merged.pop("id", None)
    _write([_point("users", {"id": str(_as_int(user_id))}, merged)])


# --------------------------------------------------- registration requests

def registration_request_create(email: str, note: str) -> int:
    request_id = _new_id()
    _write([_point(
        "registration_requests",
        {"id": str(request_id)},
        {
            "email": (email or "").strip().lower(),
            "note": note or "",
            "status": "NEW",
            "notified": 0,
            "notify_method": "",
            "created_at": now_str(),
        },
    )])
    return request_id


def registration_request_set_notified(request_id: int, method: str) -> None:
    rows = _fetch(
        f"SELECT * FROM registration_requests WHERE id = {_sql_str(_as_int(request_id))}"
        " ORDER BY time DESC LIMIT 1"
    )
    if not rows:
        return
    fields = _drop_keys(rows[0], ("time", "id"))
    fields["notified"] = 1
    fields["notify_method"] = method or ""
    _write([_point("registration_requests", {"id": rows[0].get("id")}, fields)])


def registration_request_set_status(request_id: int, status: str) -> None:
    rows = _fetch(
        f"SELECT * FROM registration_requests WHERE id = {_sql_str(_as_int(request_id))}"
        " ORDER BY time DESC LIMIT 1"
    )
    if not rows:
        return
    fields = _drop_keys(rows[0], ("time", "id"))
    fields["status"] = status or "NEW"
    _write([_point("registration_requests", {"id": rows[0].get("id")}, fields)])


def registration_requests_list(limit: int = 50) -> list[dict]:
    rows = _fetch(
        f"SELECT * FROM registration_requests ORDER BY time DESC LIMIT {int(limit) * 4}"
    )
    out = []
    for row in _latest(rows, lambda r: r.get("id")):
        out.append({
            "id": _as_int(row.get("id")),
            "email": row.get("email"),
            "note": row.get("note"),
            "status": row.get("status") or "NEW",
            "notified": _as_int(row.get("notified")),
            "notify_method": row.get("notify_method"),
            "created_at": row.get("created_at"),
        })
    out.sort(key=lambda r: (r.get("created_at") or "", r["id"]), reverse=True)
    return out[:limit]


# ------------------------------------------------------------------- trades

def trade_create(fields: dict) -> int:
    trade_id = _new_id()
    _write([_point("trades", {"id": str(trade_id)}, fields)])
    return trade_id


def trade_latest(trade_id: int) -> Optional[dict]:
    rows = _fetch(
        f"SELECT * FROM trades WHERE id = {_sql_str(_as_int(trade_id))}"
        " ORDER BY time DESC LIMIT 1"
    )
    if not rows or rows[0].get("deleted"):
        return None
    row = _public(rows[0])
    row["id"] = _as_int(row.get("id"))
    return row


def trades_for(user_id: str, limit: int = 500) -> list[dict]:
    rows = _fetch(f"SELECT * FROM trades WHERE user_id = {_sql_str(str(user_id))}")
    out = []
    for row in _latest(rows, lambda r: r.get("id")):
        if row.get("deleted"):
            continue
        row = _public(row)
        row["id"] = _as_int(row.get("id"))
        out.append(row)
    out.sort(key=lambda r: (r.get("trade_date") or "", r.get("id") or 0), reverse=True)
    return out[:limit]


def trade_delete(trade_id: int) -> None:
    row = trade_latest(trade_id)
    if row is None:
        return
    merged = {**row, "deleted": True}
    merged.pop("id", None)
    _write([_point("trades", {"id": str(_as_int(trade_id))}, merged)])


def user_delete(user_id: int) -> None:
    row = user_latest(user_id)
    if row is None:
        return
    merged = {**row, "deleted": True, "updated_at": now_str()}
    merged.pop("id", None)
    _write([_point("users", {"id": str(_as_int(user_id))}, merged)])
