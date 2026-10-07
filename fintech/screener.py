"""Stock screener: background scans over a Vietcap universe with signal and
dividend-yield filters, with progress tracking stored in SQLite."""
from __future__ import annotations

import io
import json
import threading

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from . import analysis, db, market, vietcap
from .config import SIGNAL_META

_lock = threading.Lock()
_current = {"run_id": None}
MAX_WORKERS = 6
# Serverless (Vercel) instances can be frozen/restarted mid-run; after this many
# minutes a RUNNING row is considered abandoned and can be superseded.
STALE_RUN_MINUTES = 30


def _num(value):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def resolve_universe(universe: dict) -> list[str]:
    kind = str((universe or {}).get("type") or "group")
    value = (universe or {}).get("value")
    symbols: list[str] = []
    if kind == "group":
        symbols = vietcap.fetch_vietcap_group(str(value or "VN30"))
    elif kind == "exchange":
        exchange = str(value or "HOSE").strip().upper()
        rows = db.query(
            "SELECT symbol FROM symbols WHERE exchange = ? AND (type = 'STOCK' OR type = '') ORDER BY symbol",
            (exchange,),
        )
        symbols = [r["symbol"] for r in rows]
    elif kind == "custom":
        raw = value if isinstance(value, list) else str(value or "").replace(";", ",").split(",")
        symbols = [str(s).strip().upper() for s in raw if str(s).strip()]
    else:
        raise ValueError(f"Loại universe không hợp lệ: {kind}")
    seen: set[str] = set()
    ordered: list[str] = []
    for symbol in symbols:
        symbol = symbol.strip().upper()
        if symbol and symbol not in seen and "INDEX" not in symbol:
            seen.add(symbol)
            ordered.append(symbol)
    if not ordered:
        raise ValueError("Không tìm được mã nào cho tiêu chí đã chọn")
    return ordered


def _analyze_one(symbol: str, need_dividend: bool) -> dict:
    candles, source = market.get_candles(symbol, days=300)
    payload = analysis.analyze_symbol(symbol, candles)
    price = payload["price"]
    closes = [c["c"] for c in candles]
    volumes = [float(c.get("v") or 0) for c in candles]
    avg_volume = sum(volumes[-20:]) / max(len(volumes[-20:]), 1)
    dividend_yield = None
    if need_dividend:
        funds = market.get_fundamentals(symbol, with_events=False)
        div_ps = (funds or {}).get("div_ps_ttm")
        if div_ps and price:
            dividend_yield = round(div_ps / price * 100, 2)
    signal = payload["signal"]
    levels = payload["levels"]
    buy_zone = levels.get("buy_zone") or []
    indicators = payload["indicators"]
    return {
        "symbol": symbol,
        "signal": signal["code"],
        "signal_label": signal["label"],
        "score": signal["score"],
        "price": price,
        "change_pct": payload.get("change_pct"),
        "rsi": indicators.get("rsi"),
        "avg_volume": round(avg_volume, 0),
        "dividend_yield": dividend_yield,
        "buy_zone_low": buy_zone[0] if len(buy_zone) > 1 else None,
        "buy_zone_high": buy_zone[1] if len(buy_zone) > 1 else None,
        "stop_loss": levels.get("stop_loss"),
        "target1": (levels.get("sell_points") or [{}])[0].get("price") if levels.get("sell_points") else None,
        "risk_reward": levels.get("risk_reward"),
        "fib_direction": (payload.get("fib") or {}).get("direction"),
        "reasons": (payload.get("reasons") or [])[:4],
        "source": source,
    }


def _passes(row: dict, criteria: dict) -> bool:
    signals = criteria.get("signals") or ["STRONG_BUY", "BUY"]
    if row["signal"] not in signals:
        return False
    min_score = _num(criteria.get("min_score"))
    if min_score is not None and (row["score"] is None or row["score"] < min_score):
        return False
    min_volume = _num(criteria.get("min_avg_volume"))
    if min_volume is not None and min_volume > 0 and (row["avg_volume"] or 0) < min_volume:
        return False
    price_min = _num(criteria.get("price_min"))
    if price_min is not None and (row["price"] or 0) < price_min:
        return False
    price_max = _num(criteria.get("price_max"))
    if price_max is not None and price_max > 0 and (row["price"] or 0) > price_max:
        return False
    min_div = _num(criteria.get("min_dividend_yield"))
    if min_div is not None and min_div > 0:
        exclude_unknown = criteria.get("exclude_unknown_dividend", True)
        if row["dividend_yield"] is None:
            return not exclude_unknown
        if row["dividend_yield"] < min_div:
            return False
    return True


def _execute(run_id: int, universe: dict, criteria: dict) -> None:
    try:
        symbols = resolve_universe(universe)
        settings = db.get_settings()
        max_symbols = int(_num(criteria.get("max_symbols")) or settings.get("screener_max_symbols") or 250)
        max_symbols = max(5, min(max_symbols, 1200))
        symbols = symbols[:max_symbols]
        min_div = _num(criteria.get("min_dividend_yield"))
        need_dividend = bool(min_div and min_div > 0)
        db.execute("UPDATE screen_runs SET total = ? WHERE id = ?", (len(symbols), run_id))

        processed = 0
        failed = 0
        matched = 0
        batch: list[tuple] = []

        def flush():
            nonlocal batch
            if not batch:
                return
            db.executemany(
                "INSERT INTO screen_results(run_id, symbol, signal, score, price, change_pct, dividend_yield, "
                "rsi, avg_volume, buy_zone_low, buy_zone_high, stop_loss, target1, risk_reward, extra) "
                "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                batch,
            )
            batch = []

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futures = {pool.submit(_analyze_one, symbol, need_dividend): symbol for symbol in symbols}
            for future in as_completed(futures):
                processed += 1
                try:
                    row = future.result()
                except Exception:  # noqa: BLE001 - one bad symbol must not kill the scan
                    failed += 1
                else:
                    if _passes(row, criteria):
                        matched += 1
                        batch.append(
                            (
                                run_id,
                                row["symbol"],
                                row["signal"],
                                row["score"],
                                row["price"],
                                row["change_pct"],
                                row["dividend_yield"],
                                row["rsi"],
                                row["avg_volume"],
                                row["buy_zone_low"],
                                row["buy_zone_high"],
                                row["stop_loss"],
                                row["target1"],
                                row["risk_reward"],
                                json.dumps(
                                    {
                                        "label": row["signal_label"],
                                        "reasons": row["reasons"],
                                        "fib": row["fib_direction"],
                                        "source": row["source"],
                                    },
                                    ensure_ascii=False,
                                ),
                            )
                        )
                if processed % 5 == 0 or processed == len(symbols):
                    flush()
                    db.execute(
                        "UPDATE screen_runs SET processed = ?, failed = ? WHERE id = ?",
                        (processed, failed, run_id),
                    )
        flush()
        db.execute(
            "UPDATE screen_runs SET status = 'DONE', processed = ?, failed = ?, finished_at = ? WHERE id = ?",
            (processed, failed, db.now_str(), run_id),
        )
        db.set_setting("last_screen_matched", matched)
    except Exception as exc:  # noqa: BLE001 - record failure for the UI
        db.execute(
            "UPDATE screen_runs SET status = 'ERROR', error = ?, finished_at = ? WHERE id = ?",
            (str(exc), db.now_str(), run_id),
        )
    finally:
        with _lock:
            _current["run_id"] = None


def _reconcile_stale_runs() -> None:
    """Release RUNNING rows abandoned by a dead serverless instance.

    Called while holding _lock, only when no run is active in this process.
    """
    row = db.query_one(
        "SELECT id, created_at FROM screen_runs WHERE status = 'RUNNING' ORDER BY id DESC LIMIT 1"
    )
    if not row:
        return
    try:
        started = datetime.strptime(row["created_at"] or "", "%Y-%m-%d %H:%M:%S")
        age_minutes = (datetime.now() - started).total_seconds() / 60
    except (TypeError, ValueError):
        age_minutes = STALE_RUN_MINUTES + 1
    if age_minutes < STALE_RUN_MINUTES:
        raise ValueError("Đang có phiên sàng lọc chạy — vui lòng đợi hoàn tất")
    db.execute(
        "UPDATE screen_runs SET status = 'ERROR', error = ?, finished_at = ? WHERE id = ?",
        ("Phiên sàng lọc bị gián đoạn (server khởi động lại hoặc hết thời gian xử lý).",
         db.now_str(), row["id"]),
    )


def start_run(payload: dict) -> dict:
    universe = payload.get("universe") or {}
    criteria = payload.get("criteria") or {}
    with _lock:
        if _current["run_id"] is not None:
            raise ValueError("Đang có phiên sàng lọc chạy — vui lòng đợi hoàn tất")
        _reconcile_stale_runs()
        run_id = db.execute(
            "INSERT INTO screen_runs(created_at, status, universe, criteria) VALUES(?, 'RUNNING', ?, ?)",
            (db.now_str(), json.dumps(universe, ensure_ascii=False), json.dumps(criteria, ensure_ascii=False)),
        )
        _current["run_id"] = run_id
    threading.Thread(target=_execute, args=(run_id, universe, criteria), daemon=True).start()
    return {"run_id": run_id}


def run_status(run_id: int) -> dict:
    row = db.query_one("SELECT * FROM screen_runs WHERE id = ?", (run_id,))
    if not row:
        raise ValueError("Không tìm thấy phiên sàng lọc")
    total = row["total"] or 0
    processed = row["processed"] or 0
    row["progress_pct"] = round(processed / total * 100, 1) if total else (100 if row["status"] != "RUNNING" else 0)
    return row


def run_results(run_id: int) -> list[dict]:
    rows = db.query(
        "SELECT * FROM screen_results WHERE run_id = ? ORDER BY score DESC, dividend_yield DESC",
        (run_id,),
    )
    for row in rows:
        try:
            extra = json.loads(row.get("extra") or "{}")
        except (TypeError, ValueError):
            extra = {}
        row["signal_label"] = extra.get("label") or SIGNAL_META.get(row["signal"], {}).get("label", row["signal"])
        row["reasons"] = extra.get("reasons") or []
        row["extra"] = extra
    return rows


def recent_runs(limit: int = 12) -> list[dict]:
    rows = db.query("SELECT * FROM screen_runs ORDER BY id DESC LIMIT ?", (limit,))
    for row in rows:
        count = db.query_one("SELECT COUNT(*) AS n FROM screen_results WHERE run_id = ?", (row["id"],))
        row["matched"] = int(count["n"]) if count else 0
        try:
            row["universe"] = json.loads(row.get("universe") or "{}")
            row["criteria"] = json.loads(row.get("criteria") or "{}")
        except (TypeError, ValueError):
            row["universe"], row["criteria"] = {}, {}
    return rows


def export_csv(run_id: int) -> str:
    results = run_results(run_id)
    buffer = io.StringIO()
    buffer.write("\ufeff")  # BOM for Excel
    headers = [
        "Ma", "Tin hieu", "Diem", "Gia", "%Ngay", "RSI", "KL TB 20 phien",
        "Ty suat co tuc (%)", "Vung mua duoi", "Vung mua tren", "Cat lo", "Muc tieu 1", "R/R",
    ]
    buffer.write(",".join(headers) + "\n")
    for row in results:
        cells = [
            row["symbol"], row["signal_label"], row["score"], row["price"], row["change_pct"],
            row["rsi"], row["avg_volume"], row["dividend_yield"],
            row["buy_zone_low"], row["buy_zone_high"], row["stop_loss"], row["target1"], row["risk_reward"],
        ]
        buffer.write(",".join("" if c is None else str(c) for c in cells) + "\n")
    return buffer.getvalue()
