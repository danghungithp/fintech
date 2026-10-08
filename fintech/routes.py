"""HTTP routes: pages + JSON API."""
from __future__ import annotations

from flask import Blueprint, Response, jsonify, render_template, request

from . import analysis as analysis_engine
from . import auth, candlesticks, journal, mailer
from . import db, kelly, market, portfolio, screener, vietcap
from .config import INDEX_SYMBOLS, UNIVERSE_GROUPS, EXCHANGES, ON_VERCEL, SITE_URL

bp = Blueprint("main", __name__)


def api_error(message: str, status: int = 400):
    return jsonify({"error": str(message)}), status


def _int_arg(name: str, default: int) -> int:
    try:
        return int(request.args.get(name, default))
    except (TypeError, ValueError):
        return default


# ------------------------------------------------------------------ pages

@bp.get("/")
def page_dashboard():
    return render_template("dashboard.html", active="dashboard")


@bp.get("/phan-tich")
def page_analysis():
    return render_template("analysis.html", active="analysis")


@bp.get("/sang-loc")
def page_screener():
    return render_template("screener.html", active="screener")


@bp.get("/danh-muc")
def page_portfolio():
    return render_template("portfolio.html", active="portfolio")


@bp.get("/canh-bao")
def page_alerts():
    return render_template("alerts.html", active="alerts")


@bp.get("/cai-dat")
def page_settings():
    return render_template("settings.html", active="settings")


@bp.get("/dang-nhap")
def page_login():
    return render_template("login.html", active="login")


@bp.get("/dang-ky")
def page_register():
    return render_template("register.html", active="register")


@bp.get("/so-giao-dich")
def page_journal():
    return render_template("journal.html", active="journal")


@bp.get("/quan-tri")
def page_admin():
    return render_template("admin.html", active="admin")


@bp.get("/robots.txt")
def robots_txt():
    body = "\n".join(
        [
            "User-agent: *",
            "Allow: /",
            "Disallow: /api/",
            # Private / member-only pages stay out of search indexes.
            "Disallow: /dang-nhap",
            "Disallow: /dang-ky",
            "Disallow: /so-giao-dich",
            "Disallow: /quan-tri",
            "",
            f"Sitemap: {SITE_URL}/sitemap.xml",
            "",
        ]
    )
    return Response(body, mimetype="text/plain")


@bp.get("/sitemap.xml")
def sitemap_xml():
    today = db.now_str()[:10]
    # (path, priority, changefreq) — settings page is intentionally excluded (noindex).
    urls = [
        ("/", "1.0", "daily"),
        ("/phan-tich", "0.9", "daily"),
        ("/sang-loc", "0.8", "weekly"),
        ("/canh-bao", "0.6", "daily"),
        ("/danh-muc", "0.5", "weekly"),
    ]
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for path, priority, changefreq in urls:
        lines.append(
            f"  <url><loc>{SITE_URL}{path}</loc><lastmod>{today}</lastmod>"
            f"<changefreq>{changefreq}</changefreq><priority>{priority}</priority></url>"
        )
    lines.append("</urlset>")
    return Response("\n".join(lines), mimetype="application/xml")


# --------------------------------------------------------------------- api

@bp.get("/api/health")
def api_health():
    return jsonify(
        {
            "status": "ok",
            "app": "FinViet Pro",
            "time": db.now_str(),
            "serverless": ON_VERCEL,
            "storage": "influxdb-cloud",
        }
    )


@bp.get("/api/symbols")
def api_symbols():
    term = request.args.get("query", "")
    limit = min(_int_arg("limit", 20), 100)
    try:
        return jsonify({"symbols": market.symbol_search(term, limit=limit)})
    except Exception as exc:  # noqa: BLE001
        return api_error(f"Không tải được danh sách mã: {exc}", 502)


@bp.post("/api/symbols/refresh")
def api_symbols_refresh():
    try:
        count = market.refresh_symbol_list(force=True)
        return jsonify({"ok": True, "updated": count or "danh sách đã mới"})
    except Exception as exc:  # noqa: BLE001
        return api_error(f"Làm mới danh sách thất bại: {exc}", 502)


@bp.get("/api/index/summary")
def api_index_summary():
    try:
        return jsonify({"indices": market.index_summary()})
    except Exception as exc:  # noqa: BLE001
        return api_error(str(exc), 502)


@bp.get("/api/analyze")
def api_analyze():
    symbol = (request.args.get("symbol") or "").strip().upper()
    if not symbol:
        return api_error("Thiếu tham số symbol")
    force = request.args.get("refresh") in {"1", "true", "yes"}
    settings = db.get_settings()
    days = _int_arg("days", int(settings.get("history_days") or 400))
    try:
        candles, source = market.get_candles(symbol, days=days, force=force,
                                             cache_hours=float(settings.get("cache_hours") or 6))
        fundamentals = None
        try:
            fundamentals = market.get_fundamentals(symbol)
            if fundamentals:
                fundamentals = dict(fundamentals)
                fundamentals["dividend_events"] = market.dividend_events(symbol, limit=8)
        except Exception:  # noqa: BLE001 - fundamentals are best-effort
            fundamentals = None
        meta = market.lookup_symbol(symbol)
        payload = analysis_engine.analyze_symbol(symbol, candles, settings=settings,
                                                 fundamentals=fundamentals, meta={
                                                     "exchange": meta.get("exchange"),
                                                     "organ_name": meta.get("organ_name"),
                                                     "organ_short_name": meta.get("organ_short_name"),
                                                 })
        payload["data_source"] = source
        try:
            db.save_analysis(payload)
        except Exception:  # noqa: BLE001 - persistence is best-effort
            pass
        return jsonify(payload)
    except (ValueError, vietcap.VietcapError) as exc:
        return api_error(str(exc), 400 if isinstance(exc, ValueError) else 502)
    except Exception as exc:  # noqa: BLE001
        return api_error(f"Lỗi phân tích: {exc}", 500)


@bp.get("/api/analysis/recent")
def api_recent_analyses():
    return jsonify({"items": db.recent_analyses(limit=min(_int_arg("limit", 12), 50))})


@bp.get("/api/dividends/<symbol>")
def api_dividends(symbol: str):
    symbol = symbol.strip().upper()
    try:
        events = market.dividend_events(symbol, limit=10)
        funds = market.get_fundamentals(symbol)
        return jsonify(
            {
                "symbol": symbol,
                "events": events,
                "dividend_ttm": (funds or {}).get("div_ps_ttm"),
            }
        )
    except Exception as exc:  # noqa: BLE001
        return api_error(str(exc), 502)


@bp.post("/api/kelly/calc")
def api_kelly_calc():
    body = request.get_json(silent=True) or {}
    settings = db.get_settings()

    def num(key, default=None):
        try:
            value = body.get(key)
            return float(value) if value not in (None, "") else default
        except (TypeError, ValueError):
            return default

    win_prob_pct = num("win_prob", 50.0)
    payoff = num("payoff", 2.0)
    entry = num("entry")
    stop = num("stop")
    equity = num("equity", float(settings.get("equity") or 0))
    mode = str(body.get("mode") or settings.get("kelly_mode") or "half")
    if not entry or entry <= 0:
        return api_error("Thiếu giá vào lệnh (entry)")
    if not stop or stop <= 0:
        stop = entry * 0.95
    if stop >= entry:
        return api_error("Giá cắt lỗ phải thấp hơn giá vào lệnh")
    try:
        result = kelly.recommendation(
            win_prob_pct / 100.0,
            payoff or 1.0,
            entry,
            stop,
            equity,
            mode=mode,
            risk_pct=float(settings.get("risk_pct") or 2),
            max_position_pct=float(settings.get("max_position_pct") or 20),
            lot=int(settings.get("lot") or 100),
        )
        return jsonify(result)
    except Exception as exc:  # noqa: BLE001
        return api_error(f"Lỗi tính toán Kelly: {exc}", 500)


# -------------------------------------------------------------- screener

@bp.get("/api/screener/universes")
def api_screener_universes():
    return jsonify({"groups": UNIVERSE_GROUPS, "exchanges": EXCHANGES})


@bp.post("/api/screener/run")
def api_screener_run():
    body = request.get_json(silent=True) or {}
    try:
        result = screener.start_run(body)
        return jsonify(result)
    except ValueError as exc:
        return api_error(str(exc), 409)
    except vietcap.VietcapError as exc:
        return api_error(f"Lỗi dữ liệu Vietcap: {exc}", 502)
    except Exception as exc:  # noqa: BLE001
        return api_error(f"Không khởi động được phiên sàng lọc: {exc}", 500)


@bp.get("/api/screener/runs")
def api_screener_runs():
    return jsonify({"runs": screener.recent_runs(limit=min(_int_arg("limit", 12), 40))})


@bp.get("/api/screener/runs/<int:run_id>")
def api_screener_run_status(run_id: int):
    try:
        return jsonify(screener.run_status(run_id))
    except ValueError as exc:
        return api_error(str(exc), 404)


@bp.get("/api/screener/runs/<int:run_id>/results")
def api_screener_run_results(run_id: int):
    try:
        screener.run_status(run_id)  # 404 guard
    except ValueError as exc:
        return api_error(str(exc), 404)
    return jsonify({"results": screener.run_results(run_id)})


@bp.get("/api/screener/runs/<int:run_id>/export")
def api_screener_export(run_id: int):
    try:
        screener.run_status(run_id)
    except ValueError as exc:
        return api_error(str(exc), 404)
    csv_text = screener.export_csv(run_id)
    return Response(
        csv_text,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=sang_loc_{run_id}.csv"},
    )


# -------------------------------------------------------------- portfolio

@bp.get("/api/portfolio/overview")
def api_portfolio_overview():
    try:
        positions = portfolio.positions_overview()
        return jsonify(
            {
                "positions": positions,
                "summary": portfolio.portfolio_summary(positions),
                "watchlist": portfolio.watchlist_rows(),
                "alerts_count": portfolio.alerts_count(),
            }
        )
    except Exception as exc:  # noqa: BLE001
        return api_error(f"Lỗi tải danh mục: {exc}", 500)


@bp.post("/api/portfolio/positions")
def api_position_create():
    body = request.get_json(silent=True) or {}
    try:
        position_id = portfolio.create_position(body)
        return jsonify({"ok": True, "id": position_id})
    except ValueError as exc:
        return api_error(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return api_error(f"Không thêm được vị thế: {exc}", 500)


@bp.put("/api/portfolio/positions/<int:position_id>")
def api_position_update(position_id: int):
    body = request.get_json(silent=True) or {}
    try:
        portfolio.update_position(position_id, body)
        return jsonify({"ok": True})
    except ValueError as exc:
        return api_error(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return api_error(f"Không cập nhật được vị thế: {exc}", 500)


@bp.delete("/api/portfolio/positions/<int:position_id>")
def api_position_delete(position_id: int):
    try:
        portfolio.delete_position(position_id)
        return jsonify({"ok": True})
    except Exception as exc:  # noqa: BLE001
        return api_error(str(exc), 500)


@bp.post("/api/portfolio/watch")
def api_watch_add():
    body = request.get_json(silent=True) or {}
    try:
        portfolio.add_watch(body)
        return jsonify({"ok": True})
    except ValueError as exc:
        return api_error(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return api_error(f"Không thêm được mã theo dõi: {exc}", 500)


@bp.delete("/api/portfolio/watch/<int:watch_id>")
def api_watch_remove(watch_id: int):
    try:
        portfolio.remove_watch(watch_id)
        return jsonify({"ok": True})
    except Exception as exc:  # noqa: BLE001
        return api_error(str(exc), 500)


@bp.post("/api/portfolio/scan")
def api_portfolio_scan():
    body = request.get_json(silent=True) or {}
    force = bool(body.get("force"))
    try:
        result = portfolio.scan_alerts(force=force)
        result["alerts_count"] = portfolio.alerts_count()
        return jsonify(result)
    except Exception as exc:  # noqa: BLE001
        return api_error(f"Lỗi quét cảnh báo: {exc}", 500)


# ----------------------------------------------------------------- alerts

@bp.get("/api/alerts")
def api_alerts():
    include_ack = request.args.get("include_ack") in {"1", "true", "yes"}
    limit = min(_int_arg("limit", 100), 500)
    return jsonify(
        {
            "alerts": portfolio.alerts_list(limit=limit, include_ack=include_ack),
            "unread": portfolio.alerts_count(),
        }
    )


@bp.post("/api/alerts/<int:alert_id>/ack")
def api_alert_ack(alert_id: int):
    portfolio.ack_alert(alert_id)
    return jsonify({"ok": True, "unread": portfolio.alerts_count()})


@bp.post("/api/alerts/ack-all")
def api_alert_ack_all():
    portfolio.ack_all()
    return jsonify({"ok": True, "unread": 0})


# --------------------------------------------------------------- settings

ALLOWED_SETTINGS = {
    "equity", "risk_pct", "max_position_pct", "kelly_mode", "history_days",
    "cache_hours", "scan_minutes", "min_avg_volume", "lot", "screener_max_symbols",
}


@bp.get("/api/settings")
def api_settings_get():
    return jsonify(db.get_settings())


@bp.post("/api/settings")
def api_settings_post():
    body = request.get_json(silent=True) or {}
    updated = {}
    for key, value in body.items():
        if key not in ALLOWED_SETTINGS:
            continue
        if key in {"kelly_mode"}:
            value = "full" if str(value) == "full" else "half"
        else:
            try:
                value = float(value)
            except (TypeError, ValueError):
                continue
            if value < 0:
                continue
        db.set_setting(key, value)
        updated[key] = value
    return jsonify({"ok": True, "updated": updated, "settings": db.get_settings()})


# ------------------------------------------------------------------- auth

@bp.get("/api/auth/me")
def api_auth_me():
    return jsonify({"user": auth.current_user(), "admin": auth.is_admin()})


@bp.post("/api/auth/login")
def api_auth_login():
    body = request.get_json(silent=True) or {}
    user = auth.authenticate(str(body.get("email") or ""), str(body.get("password") or ""))
    if user is None:
        return api_error("Email hoặc mật khẩu không đúng, hoặc tài khoản chưa được kích hoạt", 401)
    auth.login_user(user)
    return jsonify({"ok": True, "user": auth.current_user()})


@bp.post("/api/auth/logout")
def api_auth_logout():
    auth.logout_user()
    return jsonify({"ok": True})


@bp.post("/api/register-request")
def api_register_request():
    """Visitor asks for an account: store the request + notify the admin mailbox."""
    body = request.get_json(silent=True) or {}
    email = str(body.get("email") or "").strip()
    note = str(body.get("note") or "").strip()
    local, _, domain = email.partition("@")
    if not local or not domain or "." not in domain or " " in email or len(email) > 120:
        return api_error("Email không hợp lệ")
    try:
        result = mailer.submit_registration_request(email, note)
    except Exception as exc:  # noqa: BLE001
        return api_error(f"Không gửi được yêu cầu: {exc}", 500)
    return jsonify(result)


# ----------------------------------------------------- advanced analysis

@bp.get("/api/analysis/advanced")
@auth.login_required
def api_analysis_advanced():
    """Member-only module: trend momentum, đỉnh/đáy, nến đảo chiều, mô hình giá."""
    symbol = (request.args.get("symbol") or "").strip().upper()
    if not symbol:
        return api_error("Thiếu tham số symbol")
    settings = db.get_settings()
    days = min(_int_arg("days", 400), 400)
    try:
        candles, _source = market.get_candles(
            symbol, days=days,
            cache_hours=float(settings.get("cache_hours") or 6),
        )
        if not candles:
            return api_error(f"Không có dữ liệu giá cho {symbol}", 404)
        return jsonify(candlesticks.analyze_advanced(symbol, candles))
    except (ValueError, vietcap.VietcapError) as exc:
        return api_error(str(exc), 400 if isinstance(exc, ValueError) else 502)
    except Exception as exc:  # noqa: BLE001
        return api_error(f"Lỗi phân tích chuyên sâu: {exc}", 500)


# ---------------------------------------------------------------- journal

@bp.get("/api/trades")
@auth.login_required
def api_trades_list():
    user = auth.current_user()
    trades = journal.list_trades(user["id"])
    return jsonify({"trades": trades, "summary": journal.summary(trades)})


@bp.post("/api/trades")
@auth.login_required
def api_trades_create():
    user = auth.current_user()
    body = request.get_json(silent=True) or {}
    try:
        trade_id = journal.add_trade(user["id"], body)
    except ValueError as exc:
        return api_error(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return api_error(f"Không thêm được giao dịch: {exc}", 500)
    return jsonify({"ok": True, "id": trade_id})


@bp.delete("/api/trades/<int:trade_id>")
@auth.login_required
def api_trades_delete(trade_id: int):
    user = auth.current_user()
    if not journal.delete_trade(trade_id, user["id"]):
        return api_error("Không tìm thấy giao dịch hoặc bạn không có quyền xóa", 404)
    return jsonify({"ok": True})


# ------------------------------------------------------------------ admin

@bp.post("/api/admin/login")
def api_admin_login():
    body = request.get_json(silent=True) or {}
    if not auth.check_admin_password(str(body.get("password") or "")):
        return api_error("Mật khẩu quản trị không đúng", 401)
    auth.login_admin()
    return jsonify({"ok": True})


@bp.post("/api/admin/logout")
def api_admin_logout():
    auth.logout_admin()
    return jsonify({"ok": True})


@bp.get("/api/admin/overview")
@auth.admin_required
def api_admin_overview():
    return jsonify(
        {
            "users": db.users_list(),
            "requests": db.registration_requests_list(limit=100),
        }
    )


@bp.post("/api/admin/users")
@auth.admin_required
def api_admin_user_create():
    body = request.get_json(silent=True) or {}
    email = str(body.get("email") or "").strip().lower()
    password = str(body.get("password") or "")
    name = str(body.get("name") or "").strip()[:80]
    local, _, domain = email.partition("@")
    if not local or not domain or "." not in domain:
        return api_error("Email không hợp lệ")
    if len(password) < 6:
        return api_error("Mật khẩu cần ít nhất 6 ký tự")
    if db.user_by_email(email):
        return api_error("Email đã tồn tại trong hệ thống", 409)
    user_id = db.user_create(email, auth.hash_password(password), name or local, "user")
    # Auto-approve any pending registration request with the same email.
    for req in db.registration_requests_list(limit=100):
        if (req.get("email") or "").strip().lower() == email and (req.get("status") or "NEW") == "NEW":
            db.registration_request_set_status(req["id"], "APPROVED")
    return jsonify({"ok": True, "id": user_id})


@bp.post("/api/admin/users/<int:user_id>/active")
@auth.admin_required
def api_admin_user_active(user_id: int):
    body = request.get_json(silent=True) or {}
    if db.user_latest(user_id) is None:
        return api_error("Không tìm thấy user", 404)
    active = bool(body.get("active"))
    db.user_set_active(user_id, active)
    return jsonify({"ok": True, "active": active})


@bp.post("/api/admin/requests/<int:request_id>/status")
@auth.admin_required
def api_admin_request_status(request_id: int):
    body = request.get_json(silent=True) or {}
    status = str(body.get("status") or "").upper()
    if status not in {"APPROVED", "REJECTED"}:
        return api_error("Trạng thái không hợp lệ (APPROVED hoặc REJECTED)")
    db.registration_request_set_status(request_id, status)
    return jsonify({"ok": True})
