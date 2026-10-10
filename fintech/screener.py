"""Stock screener: background scans over a Vietcap universe with signal and
dividend-yield filters, with progress tracking stored in InfluxDB."""
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
        symbols = db.symbols_by_exchange(exchange)
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


def _analyze_one(symbol: str) -> dict:
    candles, source = market.get_candles(symbol, days=300)
    payload = analysis.analyze_symbol(symbol, candles)
    price = payload["price"]
    closes = [c["c"] for c in candles]
    volumes = [float(c.get("v") or 0) for c in candles]
    avg_volume = sum(volumes[-20:]) / max(len(volumes[-20:]), 1)
    
    funds = market.get_fundamentals(symbol, with_events=False)
    dividend_yield = None
    div_ps = (funds or {}).get("div_ps_ttm")
    if div_ps and price:
        dividend_yield = round(div_ps / price * 100, 2)
        
    signal = payload["signal"]
    levels = payload["levels"]
    buy_zone = levels.get("buy_zone") or []
    indicators = payload["indicators"]

    # CANSLIM Analysis
    try:
        from . import canslim
        vn_candles, _ = market.get_candles("VNINDEX", days=300)
        canslim_data = canslim.analyze_canslim(symbol, candles, vn_candles)
        canslim_passed = canslim_data["passed"]
    except Exception:
        canslim_passed = False

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
        "rev_growth_qoq": (funds or {}).get("rev_growth_qoq"),
        "rev_growth_yoy": (funds or {}).get("rev_growth_yoy"),
        "profit_growth_qoq": (funds or {}).get("profit_growth_qoq"),
        "profit_growth_yoy": (funds or {}).get("profit_growth_yoy"),
        "buy_zone_low": buy_zone[0] if len(buy_zone) > 1 else None,
        "buy_zone_high": buy_zone[1] if len(buy_zone) > 1 else None,
        "stop_loss": levels.get("stop_loss"),
        "target1": (levels.get("sell_points") or [{}])[0].get("price") if levels.get("sell_points") else None,
        "risk_reward": levels.get("risk_reward"),
        "fib_direction": (payload.get("fib") or {}).get("direction"),
        "reasons": (payload.get("reasons") or [])[:4],
        "source": source,
        "canslim_passed": canslim_passed,
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
    exclude_unknown = criteria.get("exclude_unknown_dividend", True)
    if min_div is not None and min_div > 0:
        if row["dividend_yield"] is None:
            return not exclude_unknown
        if row["dividend_yield"] < min_div:
            return False

    def check_growth(metric, crit_key):
        val = _num(criteria.get(crit_key))
        if val is not None:
            if row.get(metric) is None:
                return not exclude_unknown
            if row[metric] < val:
                return False
        return True

    if not check_growth("rev_growth_qoq", "min_rev_growth_qoq"): return False
    if not check_growth("rev_growth_yoy", "min_rev_growth_yoy"): return False
    if not check_growth("profit_growth_qoq", "min_profit_growth_qoq"): return False
    if not check_growth("profit_growth_yoy", "min_profit_growth_yoy"): return False

    if criteria.get("require_canslim") and not row.get("canslim_passed"):
        return False

    return True


def _execute(run_id: int, universe: dict, criteria: dict) -> None:
    try:
        symbols = resolve_universe(universe)
        settings = db.get_settings()
        max_symbols = int(_num(criteria.get("max_symbols")) or settings.get("screener_max_symbols") or 250)
        max_symbols = max(5, min(max_symbols, 1200))
        symbols = symbols[:max_symbols]
        db.screen_run_update(run_id, {"total": len(symbols)})

        processed = 0
        failed = 0
        matched = 0
        batch: list[dict] = []

        def flush():
            nonlocal batch
            if not batch:
                return
            db.screen_results_save(batch)
            batch = []

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futures = {pool.submit(_analyze_one, symbol): symbol for symbol in symbols}
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
                            {
                                "run_id": run_id,
                                "symbol": row["symbol"],
                                "signal": row["signal"],
                                "score": row["score"],
                                "price": row["price"],
                                "change_pct": row["change_pct"],
                                "dividend_yield": row["dividend_yield"],
                                "rsi": row["rsi"],
                                "avg_volume": row["avg_volume"],
                                "buy_zone_low": row["buy_zone_low"],
                                "buy_zone_high": row["buy_zone_high"],
                                "stop_loss": row["stop_loss"],
                                "target1": row["target1"],
                                "risk_reward": row["risk_reward"],
                                "extra": json.dumps(
                                    {
                                        "label": row["signal_label"],
                                        "reasons": row["reasons"],
                                        "fib": row["fib_direction"],
                                        "source": row["source"],
                                        "rev_growth_qoq": row.get("rev_growth_qoq"),
                                        "rev_growth_yoy": row.get("rev_growth_yoy"),
                                        "profit_growth_qoq": row.get("profit_growth_qoq"),
                                        "profit_growth_yoy": row.get("profit_growth_yoy"),
                                    },
                                    ensure_ascii=False,
                                ),
                            }
                        )
                if processed % 5 == 0 or processed == len(symbols):
                    flush()
                    db.screen_run_update(run_id, {"processed": processed, "failed": failed})
        flush()
        db.screen_run_update(
            run_id,
            {
                "status": "DONE",
                "processed": processed,
                "failed": failed,
                "finished_at": db.now_str(),
            },
        )
        db.set_setting("last_screen_matched", matched)
    except Exception as exc:  # noqa: BLE001 - record failure for the UI
        db.screen_run_update(
            run_id,
            {"status": "ERROR", "error": str(exc), "finished_at": db.now_str()},
        )
    finally:
        with _lock:
            _current["run_id"] = None


def _reconcile_stale_runs() -> None:
    """Release RUNNING rows abandoned by a dead serverless instance.

    Called while holding _lock, only when no run is active in this process.
    """
    row = db.screen_run_latest_running()
    if not row:
        return
    try:
        started = datetime.strptime(row["created_at"] or "", "%Y-%m-%d %H:%M:%S")
        age_minutes = (datetime.now() - started).total_seconds() / 60
    except (TypeError, ValueError):
        age_minutes = STALE_RUN_MINUTES + 1
    if age_minutes < STALE_RUN_MINUTES:
        raise ValueError("Đang có phiên sàng lọc chạy — vui lòng đợi hoàn tất")
    db.screen_run_update(
        row["id"],
        {
            "status": "ERROR",
            "error": "Phiên sàng lọc bị gián đoạn (server khởi động lại hoặc hết thời gian xử lý).",
            "finished_at": db.now_str(),
        },
    )


def start_run(payload: dict) -> dict:
    universe = payload.get("universe") or {}
    criteria = payload.get("criteria") or {}
    with _lock:
        if _current["run_id"] is not None:
            raise ValueError("Đang có phiên sàng lọc chạy — vui lòng đợi hoàn tất")
        _reconcile_stale_runs()
        run_id = db.screen_run_create(
            json.dumps(universe, ensure_ascii=False),
            json.dumps(criteria, ensure_ascii=False),
        )
        _current["run_id"] = run_id
    threading.Thread(target=_execute, args=(run_id, universe, criteria), daemon=True).start()
    return {"run_id": run_id}


def run_status(run_id: int) -> dict:
    row = db.screen_run_latest(run_id)
    if not row:
        raise ValueError("Không tìm thấy phiên sàng lọc")
    total = row["total"] or 0
    processed = row["processed"] or 0
    row["progress_pct"] = round(processed / total * 100, 1) if total else (100 if row["status"] != "RUNNING" else 0)
    return row


def run_results(run_id: int) -> list[dict]:
    rows = db.screen_results_for_run(run_id)
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
    ids = db.screen_run_ids(limit)
    runs = db.screen_runs_latest(ids)
    counts = db.screen_results_counts(ids)
    rows: list[dict] = []
    for run_id in sorted(ids, reverse=True):
        row = runs.get(run_id)
        if row is None:
            continue
        row["matched"] = counts.get(run_id, 0)
        try:
            row["universe"] = json.loads(row.get("universe") or "{}")
            row["criteria"] = json.loads(row.get("criteria") or "{}")
        except (TypeError, ValueError):
            row["universe"], row["criteria"] = {}, {}
        rows.append(row)
    return rows


def export_csv(run_id: int) -> str:
    results = run_results(run_id)
    buffer = io.StringIO()
    buffer.write("\ufeff")  # BOM for Excel
    headers = [
        "Ma", "Tin hieu", "Diem", "Gia", "%Ngay", "RSI", "KL TB 20 phien",
        "Ty suat co tuc (%)", "DT Quy (%)", "DT Nam (%)", "LN Quy (%)", "LN Nam (%)",
        "Vung mua duoi", "Vung mua tren", "Cat lo", "Muc tieu 1", "R/R",
    ]
    buffer.write(",".join(headers) + "\n")
    for row in results:
        extra = row.get("extra") or {}
        cells = [
            row["symbol"], row["signal_label"], row["score"], row["price"], row["change_pct"],
            row["rsi"], row["avg_volume"], row["dividend_yield"],
            extra.get("rev_growth_qoq"), extra.get("rev_growth_yoy"),
            extra.get("profit_growth_qoq"), extra.get("profit_growth_yoy"),
            row["buy_zone_low"], row["buy_zone_high"], row["stop_loss"], row["target1"], row["risk_reward"],
        ]
        buffer.write(",".join("" if c is None else str(c) for c in cells) + "\n")
    return buffer.getvalue()
