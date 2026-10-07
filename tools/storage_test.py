"""Integration test for the InfluxDB storage layer (fintech/db.py).

Runs against an isolated bucket (fintech_test by default — created on the
fly) so real data is never touched:

    python tools/storage_test.py
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Must be set before importing fintech.config (env wins over .env values).
os.environ["INFLUXDB_BUCKET"] = os.environ.get("FINTECH_TEST_BUCKET", "fintech_test")

from fintech import db  # noqa: E402
from fintech.config import INFLUX_BUCKET, INFLUX_HOST, INFLUX_ORG, INFLUX_TOKEN  # noqa: E402

PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = ""):
    tag = "PASS" if ok else "FAIL"
    print(f"[{tag}] {name}" + (f" — {detail}" if detail else ""))
    (PASSED if ok else FAILED).append(name)


def ensure_bucket() -> None:
    """Drop (if present) and recreate the isolated test bucket — a clean slate."""

    def api(method: str, path: str, body: dict | None = None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(INFLUX_HOST.rstrip("/") + path, data=data, method=method)
        req.add_header("Authorization", f"Token {INFLUX_TOKEN}")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.status, json.loads(resp.read().decode() or "{}")
        except urllib.error.HTTPError as exc:
            return exc.code, {}

    status, payload = api("GET", f"/api/v2/buckets?name={INFLUX_BUCKET}")
    existing = payload.get("buckets") or []
    for bucket in existing:
        drop_status, _ = api("DELETE", f"/api/v2/buckets/{bucket.get('id')}")
        print(f"dropped old bucket {INFLUX_BUCKET}: status={drop_status}")
    _, orgs = api("GET", f"/api/v2/orgs?org={INFLUX_ORG}")
    org_id = next((o.get("id") for o in (orgs.get("orgs") or []) if o.get("name") == INFLUX_ORG), None)
    status, _ = api("POST", "/api/v2/buckets", {"orgID": org_id, "name": INFLUX_BUCKET, "retentionRules": []})
    print(f"created bucket {INFLUX_BUCKET}: status={status}")
    if status not in (200, 201):
        raise SystemExit(f"cannot create test bucket {INFLUX_BUCKET}")


def main() -> None:
    print(f"== storage test @ bucket {INFLUX_BUCKET} ==\n")
    ensure_bucket()

    # ------------------------------------------------------------ settings
    merged = db.get_settings()
    check("settings defaults merged", merged.get("equity") == 500000000.0, f"equity={merged.get('equity')}")
    check("missing setting -> None", db.get_setting("khong_ton_tai") is None)

    db.set_setting("risk_pct", 1.5)
    db.set_setting("kelly_mode", "full")
    check("setting roundtrip", db.get_setting("risk_pct") == 1.5, f"risk_pct={db.get_setting('risk_pct')}")
    check("settings merge keeps defaults", db.get_settings().get("kelly_mode") == "full")

    # ------------------------------------------------------------- symbols
    records = [
        {"symbol": "FPT", "exchange": "HOSE", "type": "STOCK", "organ_name": "CTCP FPT", "organ_short_name": "FPT"},
        {"symbol": "VCB", "exchange": "HOSE", "type": "STOCK", "organ_name": "Ngân hàng TMCP Ngoại thương Việt Nam", "organ_short_name": "Vietcombank"},
        {"symbol": "PVS", "exchange": "HNX", "type": "STOCK", "organ_name": "CTCP Dịch vụ Kỹ thuật Dầu khí", "organ_short_name": "PVS"},
        {"symbol": "SBT", "exchange": "UPCOM", "type": "STOCK", "organ_name": "CTCP Bourbon Tây Ninh", "organ_short_name": "SBT"},
        {"symbol": "E1VFVN30", "exchange": "HOSE", "type": "ETF", "organ_name": "Quỹ ETF VN30", "organ_short_name": "E1VFVN30"},
    ]
    check("save symbols", db.save_symbols(records) == 5)
    stats = db.symbol_stats()
    check("symbol stats", stats and stats["n"] == 5 and stats["updated"], f"{stats}")

    hits = db.search_symbols("FPT")
    check("search exact first", hits and hits[0]["symbol"] == "FPT" and hits[0]["exchange"] == "HOSE", f"{[h['symbol'] for h in hits]}")
    viet = db.search_symbols("ngoại thương")
    check("search diacritics", any(h["symbol"] == "VCB" for h in viet), f"{[h['symbol'] for h in viet]}")
    everything = db.search_symbols("")
    check("search empty -> STOCK only, HOSE first",
          everything and everything[0]["exchange"] == "HOSE" and all(h["symbol"] != "E1VFVN30" for h in everything),
          f"{[h['symbol'] for h in everything]}")
    check("meta lookup", (db.symbol_meta("vcb") or {}).get("organ_short_name") == "Vietcombank")
    check("symbols_by_exchange", db.symbols_by_exchange("HOSE") == ["FPT", "VCB"], f"{db.symbols_by_exchange('HOSE')}")

    db.save_symbols([r for r in records if r["symbol"] != "PVS"])
    check("new generation replaces list", db.symbol_stats()["n"] == 4 and db.symbol_meta("PVS") is None)

    # ------------------------------------------------------------- candles
    candles = [
        {"t": "2026-09-25", "o": 100, "h": 105, "l": 99, "c": 104, "v": 1200},
        {"t": "2026-09-26", "o": 104, "h": 108, "l": 103, "c": 107, "v": 1500},
        {"t": "2026-09-29", "o": 107, "h": 110, "l": 106, "c": 109, "v": 1700},
    ]
    db.save_candles("fpt", candles)
    loaded = db.load_candles("FPT", limit=10)
    check("candles roundtrip", [c["t"] for c in loaded] == [c["t"] for c in candles], f"{[c['c'] for c in loaded]}")
    check("candle value", loaded[2]["c"] == 109 and loaded[0]["v"] == 1200)

    db.save_candles("FPT", candles)  # unchanged -> no rewrite
    check("unchanged re-save is deduped", db.candle_stats("FPT")["n"] == 3)

    changed = [dict(c) for c in candles]
    changed[2]["c"] = 111.5
    db.save_candles("FPT", changed)
    loaded = db.load_candles("FPT", limit=10)
    check("candle update wins", len(loaded) == 3 and loaded[2]["c"] == 111.5 and db.candle_stats("FPT")["n"] == 3)
    check("candle stats last date", db.candle_stats("FPT")["last_date"] == "2026-09-29")
    check("empty candle stats", db.candle_stats("ZZZ") == {"last_date": None, "n": 0})

    # --------------------------------------------------------- cache stamps
    db.save_cache_stamp("FPT")
    stamp = db.load_cache_stamp("fpt")
    check("cache stamp roundtrip", bool(stamp) and len(stamp) == 19, f"{stamp}")
    check("cache stamp missing", db.load_cache_stamp("ZZZ") is None)

    # --------------------------------------------------------- fundamentals
    db.save_fundamentals("FPT", {
        "div_ps_ttm": 2000.0, "market_cap": 150000.0, "rating": "MUA",
        "target_price": 135000.0, "sector": "Công nghệ", "extra": {"foreign_pct": 30.5},
    })
    funds = db.load_fundamentals("fpt")
    check("fundamentals roundtrip",
          funds and funds["rating"] == "MUA" and funds["extra"].get("foreign_pct") == 30.5 and funds["sector"] == "Công nghệ")
    db.save_fundamentals("FPT", {"rating": "NẮM GIỮ", "extra": {}})
    check("fundamentals latest wins", db.load_fundamentals("FPT")["rating"] == "NẮM GIỮ" and db.load_fundamentals("FPT")["div_ps_ttm"] is None)

    # ------------------------------------------------------ dividend events
    db.save_dividend_events("FPT", [
        {"ex_date": "2026-06-12", "amount": 1000.0, "title": "Cổ tức tiền mặt 10%"},
        {"ex_date": "2025-12-01", "amount": 500.0, "title": None},
    ])
    events = db.load_dividend_events("fpt")
    check("dividends ordered desc", [e["ex_date"] for e in events] == ["2026-06-12", "2025-12-01"], f"{[e['title'] for e in events]}")
    db.save_dividend_events("FPT", [{"ex_date": "2026-06-12", "amount": 1200.0, "title": "Điều chỉnh"}])
    events = db.load_dividend_events("FPT")
    check("dividend deduped by ex_date", len(events) == 2 and events[0]["amount"] == 1200.0)

    # -------------------------------------------------------------- analyses
    payload = {
        "symbol": "FPT", "price": 120000.0,
        "signal": {"code": "BUY", "score": 42.0, "label": "MUA"},
        "levels": {"buy_zone": [115000.0, 118000.0], "stop_loss": 110000.0,
                   "sell_points": [{"price": 130000.0}, {"price": 140000.0}]},
    }
    db.save_analysis(payload)
    recent = db.recent_analyses(limit=5)
    check("recent analyses", recent and recent[0]["symbol"] == "FPT" and isinstance(recent[0]["id"], int),
          f"id={recent[0]['id'] if recent else None} target1={recent[0].get('target1') if recent else None}")
    check("recent analyses fields", recent[0]["signal"] == "BUY" and recent[0]["buy_zone_low"] == 115000.0 and recent[0]["target1"] == 130000.0)
    last = db.last_analysis("fpt")
    check("last analysis payload", last and json.loads(last["payload"])["symbol"] == "FPT" and last["target2"] == 140000.0)

    # ----------------------------------------------------------- screen runs
    run_id = db.screen_run_create(json.dumps({"type": "custom", "value": "FPT,VCB"}), json.dumps({"signals": ["BUY"]}))
    check("run created", isinstance(run_id, int) and run_id > 0, f"id={run_id}")
    run = db.screen_run_latest(run_id)
    check("run initial status", run and run["status"] == "RUNNING" and run["total"] == 0)

    db.screen_run_update(run_id, {"total": 2})
    db.screen_results_save([
        {"run_id": run_id, "symbol": "FPT", "signal": "BUY", "score": 42.0, "price": 120000.0,
         "change_pct": 1.2, "dividend_yield": None, "rsi": 55.0, "avg_volume": 900000.0,
         "buy_zone_low": 115000.0, "buy_zone_high": 118000.0, "stop_loss": 110000.0,
         "target1": 130000.0, "risk_reward": 2.0, "extra": json.dumps({"label": "MUA", "reasons": ["fib"], "fib": "up", "source": "vietcap"}, ensure_ascii=False)},
        {"run_id": run_id, "symbol": "VCB", "signal": "BUY", "score": 55.0, "price": 90000.0,
         "change_pct": 0.5, "dividend_yield": 3.2, "rsi": 60.0, "avg_volume": 1200000.0,
         "buy_zone_low": 88000.0, "buy_zone_high": 89500.0, "stop_loss": 85000.0,
         "target1": 98000.0, "risk_reward": 2.5, "extra": json.dumps({"label": "MUA"}, ensure_ascii=False)},
    ])
    results = db.screen_results_for_run(run_id)
    check("results sorted score desc", [r["symbol"] for r in results] == ["VCB", "FPT"], f"{[(r['symbol'], r['score']) for r in results]}")
    check("results row fields", results[0]["dividend_yield"] == 3.2 and results[0]["run_id"] == run_id and results[1]["dividend_yield"] is None)

    counts = db.screen_results_counts([run_id, 999999])
    check("results counts", counts.get(run_id) == 2 and 999999 not in counts, f"{counts}")

    db.screen_run_update(run_id, {"status": "DONE", "processed": 2, "finished_at": db.now_str()})
    check("run done", db.screen_run_latest(run_id)["status"] == "DONE")
    check("no running runs", db.screen_run_latest_running() is None)

    stale_id = db.screen_run_create(json.dumps({}), json.dumps({}))
    check("running run detected", (db.screen_run_latest_running() or {}).get("id") == stale_id)
    db.screen_run_update(stale_id, {"status": "ERROR", "error": "stale", "finished_at": db.now_str()})

    ids = db.screen_run_ids(10)
    runs = db.screen_runs_latest(ids)
    check("recent run ids", set(ids) >= {run_id, stale_id} and runs[run_id]["status"] == "DONE",
          f"ids={ids}")

    # -------------------------------------------------------------- positions
    pos1 = db.position_create({"symbol": "FPT", "quantity": 100, "avg_cost": 110000.0, "buy_date": "2026-09-01",
                               "stop_loss": 105000.0, "take_profit": None, "note": "lô đầu",
                               "status": "OPEN", "created_at": db.now_str(), "updated_at": db.now_str()})
    pos2 = db.position_create({"symbol": "VCB", "quantity": 200, "avg_cost": 88000.0, "buy_date": "2026-09-10",
                               "stop_loss": None, "take_profit": None, "note": None,
                               "status": "OPEN", "created_at": db.now_str(), "updated_at": db.now_str()})
    open_rows = db.positions_open()
    check("positions open ordered", [p["id"] for p in open_rows] == [pos1, pos2], f"{[(p['symbol'], p['id']) for p in open_rows]}")
    check("position fields", open_rows[0]["note"] == "lô đầu" and open_rows[1]["take_profit"] is None)

    db.position_put(pos1, {"quantity": 150, "avg_cost": 108000.0, "stop_loss": 104000.0,
                           "take_profit": 125000.0, "note": "lô đầu", "status": "OPEN"})
    row = db.position_latest(pos1)
    check("position update merge", row["quantity"] == 150 and row["avg_cost"] == 108000.0 and row["created_at"] == open_rows[0]["created_at"],
          f"qty={row['quantity']} created_at kept")

    db.position_delete(pos2)
    check("position delete (tombstone)", db.position_latest(pos2) is None and [p["id"] for p in db.positions_open()] == [pos1])

    # -------------------------------------------------------------- watchlist
    w1 = db.watch_add("SSI", "ngân hàng chứng khoán", 45000.0)
    w2 = db.watch_add("HPG", None, None)
    rows = db.watchlist_all()
    check("watchlist add", len(rows) == 2 and rows[0]["id"] == w2 and rows[1]["id"] == w1)

    w1_again = db.watch_add("SSI", "cập nhật ghi chú", 47000.0)
    rows = db.watchlist_all()
    check("watch upsert keeps id/created_at", w1_again == w1 and len(rows) == 2 and rows[1]["note"] == "cập nhật ghi chú",
          f"created_at={rows[1]['created_at']}")

    db.watch_remove(w1)
    rows = db.watchlist_all()
    check("watch remove", len(rows) == 1 and rows[0]["symbol"] == "HPG")

    w1_new = db.watch_add("SSI", "quay lại", None)
    check("re-add after remove gets new id", w1_new != w1 and len(db.watchlist_all()) == 2)

    # ----------------------------------------------------------------- alerts
    db.alert_upsert("FPT", "STOP_LOSS", "critical", "CẮT LỖ FPT: giá 104,000 đã chạm 105,000", 104000.0)
    check("alert created", db.alerts_count() == 1)
    first = db.alerts_list(limit=10)
    alert_id = first[0]["id"]
    check("alert public shape", first[0]["type"] == "STOP_LOSS" and first[0]["acknowledged"] == 0 and isinstance(alert_id, int))

    db.alert_upsert("FPT", "STOP_LOSS", "critical", "CẮT LỖ FPT (cập nhật): 103,000", 103000.0)
    second = db.alerts_list(limit=10)
    check("rescan updates same alert", db.alerts_count() == 1 and second[0]["id"] == alert_id and "103,000" in second[0]["message"])

    db.alert_ack(alert_id)
    check("alert ack", db.alerts_count() == 0)
    db.alert_upsert("FPT", "STOP_LOSS", "critical", "CẮT LỖ FPT lần 3", 102000.0)
    acked = db.alerts_list(limit=10, include_ack=True)
    check("rescan preserves acknowledged", db.alerts_count() == 0 and acked[0]["id"] == alert_id and acked[0]["acknowledged"] == 1)

    db.alert_upsert("VCB", "BUY_SIGNAL", "medium", "TÍN HIỆU MUA VCB", 90000.0)
    check("separate alert per key", db.alerts_count() == 1)
    db.alert_ack_all()
    check("ack all", db.alerts_count() == 0 and len(db.alerts_list(limit=10, include_ack=True)) == 2)

    # -------------------------------------------------------------- init/touch
    db.init_db()
    after = db.positions_open()
    check("init_db touch keeps state", len(after) == 1 and after[0]["id"] == pos1 and db.alerts_count() == 0)

    print(f"\n== Kết quả: {len(PASSED)} PASS / {len(FAILED)} FAIL ==")
    if FAILED:
        print("FAILED:", ", ".join(FAILED))
        sys.exit(1)


if __name__ == "__main__":
    main()
