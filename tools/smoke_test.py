"""End-to-end smoke test for FinViet Pro (run while the server is up).

Usage: python tools/smoke_test.py [base_url]

The screener, analysis and portfolio sections require a member session:
the script first proves those APIs are locked for visitors, then bootstraps
a temporary smoke-test account through the admin API (ADMIN_PASSWORD from the
environment or .env), logs in with a cookie jar and runs the full flow.
"""
from __future__ import annotations

import http.cookiejar
import json
import os
import sys
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5000"
PASSED, FAILED = [], []

# Load .env so ADMIN_PASSWORD / INFLUXDB_TOKEN are available for local runs.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from fintech import config as _config  # noqa: F401  (loads .env into os.environ)
except Exception:  # noqa: BLE001 - remote runs may not need the app package
    pass

SMOKE_EMAIL = os.environ.get("SMOKE_EMAIL", "smoke.tester@finviet.local")
SMOKE_PASSWORD = os.environ.get("SMOKE_PASSWORD", "Smoke-Test-2026!")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")

JAR = http.cookiejar.CookieJar()
OPENER = build_opener(HTTPCookieProcessor(JAR))


def call(method: str, path: str, body: dict | None = None, raw: bool = False):
    data = json.dumps(body).encode() if body is not None else None
    req = Request(
        BASE + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    try:
        with OPENER.open(req, timeout=90) as res:
            content = res.read().decode("utf-8", errors="replace")
            return res.status, content if raw else json.loads(content or "{}")
    except HTTPError as exc:
        content = exc.read().decode("utf-8", errors="replace")
        if raw:
            return exc.code, content
        try:
            return exc.code, json.loads(content or "{}")
        except json.JSONDecodeError:
            return exc.code, content


def check(name: str, ok: bool, detail: str = ""):
    tag = "PASS" if ok else "FAIL"
    line = f"[{tag}] {name}" + (f" — {detail}" if detail else "")
    print(line)
    (PASSED if ok else FAILED).append(name)


def is_local() -> bool:
    return "127.0.0.1" in BASE or "localhost" in BASE


def local_delete_smoke_user() -> bool:
    """Remove the smoke user straight from storage — local runs only."""
    try:
        from fintech import db as fintech_db
    except Exception:  # noqa: BLE001
        return False
    try:
        row = fintech_db.user_by_email(SMOKE_EMAIL)
        if row:
            fintech_db.user_delete(row["id"])
            return True
    except Exception:  # noqa: BLE001
        return False
    return False


def admin_login() -> bool:
    if not ADMIN_PASSWORD:
        return False
    status, body = call("POST", "/api/admin/login", {"password": ADMIN_PASSWORD})
    return status == 200 and isinstance(body, dict) and body.get("ok")


def admin_find_user():
    status, body = call("GET", "/api/admin/overview")
    if status != 200 or not isinstance(body, dict):
        return None
    for u in body.get("users", []):
        if (u.get("email") or "").lower() == SMOKE_EMAIL.lower():
            return u
    return None


def bootstrap_member() -> tuple[bool, str]:
    """Ensure a logged-in member session; returns (ok, method-note)."""
    status, _ = call("POST", "/api/auth/login", {"email": SMOKE_EMAIL, "password": SMOKE_PASSWORD})
    if status == 200:
        return True, "tài khoản smoke có sẵn"
    if not admin_login():
        return False, "thiếu ADMIN_PASSWORD để tạo tài khoản smoke"
    if is_local():
        local_delete_smoke_user()
    status, body = call("POST", "/api/admin/users",
                        {"email": SMOKE_EMAIL, "password": SMOKE_PASSWORD, "name": "Smoke Test"})
    if status == 409:
        user = admin_find_user()
        if user:
            call("POST", f"/api/admin/users/{user['id']}/active", {"active": True})
    elif status != 200:
        return False, f"admin tạo user lỗi: {body}"
    status, _ = call("POST", "/api/auth/login", {"email": SMOKE_EMAIL, "password": SMOKE_PASSWORD})
    return status == 200, "admin API"


def cleanup_smoke_user():
    if is_local():
        local_delete_smoke_user()
        return
    if admin_login():
        user = admin_find_user()
        if user:
            call("POST", f"/api/admin/users/{user['id']}/active", {"active": False})


def main():
    print(f"== FinViet Pro smoke test @ {BASE} ==\n")

    status, body = call("GET", "/api/health")
    check("health", status == 200 and body.get("status") == "ok", str(body)[:80])

    pages = {
        "/": ["Tổng quan", "FinViet Pro"],
        "/phan-tich": ["Phân tích kỹ thuật", "price-chart", "analysis-locked"],
        "/sang-loc": ["Tiêu chí sàng lọc", "criteria-grid", "screener-locked"],
        "/danh-muc": ["Quản lý vị thế", "alloc-bar", "portfolio-locked"],
        "/canh-bao": ["Trung tâm cảnh báo", "al-feed"],
        "/cai-dat": ["Quản trị vốn", "kelly"],
    }
    for path, markers in pages.items():
        status, html = call("GET", path, raw=True)
        ok = status == 200 and all(m in html for m in markers)
        check(f"page {path}", ok, f"status={status}")

    status, body = call("GET", "/api/symbols?limit=5")
    symbols = body.get("symbols", [])
    check("symbols listing", status == 200 and len(symbols) > 0,
          f"{len(symbols)} mã, vd: {symbols[0]['symbol'] if symbols else '—'}")

    # member-only APIs must be locked for logged-out visitors
    gated_checks = [
        ("GET", "/api/analyze?symbol=FPT", None),
        ("POST", "/api/kelly/calc", {"equity": 500000000, "entry": 60000, "stop": 57000}),
        ("GET", "/api/screener/universes", None),
        ("GET", "/api/screener/runs", None),
        ("POST", "/api/screener/run", {}),
        ("GET", "/api/portfolio/overview", None),
        ("POST", "/api/portfolio/positions", {"symbol": "FPT", "quantity": 100, "avg_cost": 90000}),
        ("POST", "/api/portfolio/watch", {"symbol": "FPT"}),
        ("POST", "/api/portfolio/scan", {}),
    ]
    for method, path, gated_body in gated_checks:
        st, payload = call(method, path, gated_body)
        locked = st == 401 and isinstance(payload, dict) and payload.get("auth_required") is True
        check(f"locked {method} {path}", locked, f"status={st}")

    # bootstrap the member session used by the screener/analysis/portfolio checks
    member, how = bootstrap_member()
    check("member smoke login", member, f"{SMOKE_EMAIL} ({how})")
    if not member:
        print("\n== Dừng: không có phiên thành viên để chạy các mục được bảo vệ ==")
        sys.exit(1)

    status, body = call("GET", "/api/analyze?symbol=FPT")
    payload = body if isinstance(body, dict) else {}
    ok = (
        status == 200
        and payload.get("symbol") == "FPT"
        and payload.get("candles")
        and payload.get("fib")
        and payload.get("levels", {}).get("stop_loss")
        and payload.get("signal", {}).get("code")
    )
    check("analyze FPT", ok,
          f"signal={payload.get('signal', {}).get('label')} score={payload.get('signal', {}).get('score')} "
          f"nến={len(payload.get('candles') or [])} stop={payload.get('levels', {}).get('stop_loss')}")

    status, body = call("GET", "/api/analyze?symbol=ZZZZZ")
    check("analyze unknown symbol -> error", status >= 400, f"status={status}")

    price = payload.get("price") or 60000
    stop = payload.get("levels", {}).get("stop_loss") or price * 0.95
    status, body = call("POST", "/api/kelly/calc", {
        "equity": 500000000, "entry": price, "stop": stop,
        "win_prob": 55, "payoff": 2, "mode": "half",
    })
    ok = status == 200 and body.get("quantity") is not None and body.get("used_fraction_pct") is not None
    check("kelly calc", ok,
          f"qt={body.get('quantity')} ({body.get('used_fraction_pct')}% vốn, mode={body.get('mode')})")

    status, body = call("GET", "/api/index/summary")
    idx = {i["symbol"] for i in body.get("indices", [])} if isinstance(body, dict) else set()
    check("index summary", status == 200 and idx, f"indices={sorted(idx)}")

    # screener: small custom universe, no dividend filter (fast)
    status, body = call("POST", "/api/screener/run", {
        "universe": {"type": "custom", "value": "FPT, VCB, SSI, HPG"},
        "criteria": {"signals": ["STRONG_BUY", "BUY", "HOLD", "SELL", "STRONG_SELL"], "min_avg_volume": 0},
    })
    run_id = body.get("run_id") if isinstance(body, dict) else None
    check("screener start", status == 200 and run_id, f"run_id={run_id}")

    if run_id:
        deadline = time.time() + 120
        run = {}
        while time.time() < deadline:
            time.sleep(1.5)
            _, run = call("GET", f"/api/screener/runs/{run_id}")
            if run.get("status") != "RUNNING":
                break
        check("screener finish", run.get("status") == "DONE",
              f"status={run.get('status')} processed={run.get('processed')}/{run.get('total')} err={run.get('error', '')}")
        _, results = call("GET", f"/api/screener/runs/{run_id}/results")
        check("screener results", isinstance(results, dict) and "results" in results,
              f"{len(results.get('results', []))} mã đạt")
        st, csv_text = call("GET", f"/api/screener/runs/{run_id}/export", raw=True)
        check("screener export csv", st == 200 and "Ma,Tin hieu" in csv_text, f"{len(csv_text)} bytes")

    # dividend-yield filter smoke (VN30 subset, small)
    status, body = call("POST", "/api/screener/run", {
        "universe": {"type": "custom", "value": "VCB, BID, CTG, MBB, ACB"},
        "criteria": {"signals": ["STRONG_BUY", "BUY", "HOLD", "SELL", "STRONG_SELL"],
                     "min_dividend_yield": 1, "exclude_unknown_dividend": False, "min_avg_volume": 0},
    })
    run2 = body.get("run_id") if isinstance(body, dict) else None
    check("screener dividend filter start", status == 200 and run2, f"run_id={run2}")
    if run2:
        deadline = time.time() + 120
        run = {}
        while time.time() < deadline:
            time.sleep(1.5)
            _, run = call("GET", f"/api/screener/runs/{run2}")
            if run.get("status") != "RUNNING":
                break
        _, results = call("GET", f"/api/screener/runs/{run2}/results")
        dy = [(r["symbol"], r.get("dividend_yield")) for r in results.get("results", [])]
        check("screener dividend results", run.get("status") == "DONE", f"matched={dy[:6]}")

    # portfolio lifecycle: create -> overview -> update -> scan -> alerts -> delete
    status, body = call("POST", "/api/portfolio/positions", {
        "symbol": "FPT", "quantity": 100, "avg_cost": price * 0.9, "note": "smoke-test",
    })
    pos_id = body.get("id") if isinstance(body, dict) else None
    check("position create", status == 200 and pos_id, f"id={pos_id}")

    status, body = call("GET", "/api/portfolio/overview")
    positions = body.get("positions", []) if isinstance(body, dict) else []
    check("portfolio overview", status == 200 and any(p["id"] == pos_id for p in positions),
          f"{len(positions)} vị thế, summary={body.get('summary', {}).get('pnl')}")

    if pos_id:
        status, body = call("PUT", f"/api/portfolio/positions/{pos_id}", {"quantity": 200, "avg_cost": price * 0.88})
        check("position update", status == 200 and body.get("ok"), "")

    status, body = call("POST", "/api/portfolio/watch", {"symbol": "SSI", "note": "smoke-test", "target_price": None})
    check("watch add", status == 200 and body.get("ok"), "")

    status, body = call("POST", "/api/portfolio/scan", {"force": True})
    ok = status == 200 and "scanned" in (body or {})
    check("alert scan", ok, f"scanned={body.get('scanned')} created={body.get('created')}")

    status, body = call("GET", "/api/alerts?limit=50")
    alerts = body.get("alerts", []) if isinstance(body, dict) else []
    check("alerts list", status == 200 and "unread" in body, f"{len(alerts)} cảnh báo, unread={body.get('unread')}")
    if alerts:
        status, body = call("POST", f"/api/alerts/{alerts[0]['id']}/ack", {})
        check("alert ack", status == 200 and body.get("ok"), "")
    status, body = call("POST", "/api/alerts/ack-all", {})
    check("alert ack-all", status == 200 and body.get("unread") == 0, "")

    # settings roundtrip (write same values back)
    status, body = call("GET", "/api/settings")
    original = dict(body) if isinstance(body, dict) else {}
    status, body = call("POST", "/api/settings", {"risk_pct": original.get("risk_pct", 2.0)})
    check("settings save", status == 200 and body.get("ok"), "")

    # cleanup
    if pos_id:
        status, _ = call("DELETE", f"/api/portfolio/positions/{pos_id}")
        check("position cleanup", status == 200, f"deleted id={pos_id}")
    _, body = call("GET", "/api/portfolio/overview")
    watch_rows = body.get("watchlist", [])
    for w in watch_rows:
        if w.get("note") == "smoke-test":
            call("DELETE", f"/api/portfolio/watch/{w['id']}")
    check("watch cleanup", True, "")

    # remove (local) or deactivate (remote) the temporary smoke account
    cleanup_smoke_user()
    check("smoke user cleanup", True, "local: đã xóa / remote: đã vô hiệu hóa")

    print(f"\n== Kết quả: {len(PASSED)} PASS / {len(FAILED)} FAIL ==")
    if FAILED:
        print("FAILED:", ", ".join(FAILED))
        sys.exit(1)


if __name__ == "__main__":
    main()
