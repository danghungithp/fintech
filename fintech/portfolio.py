"""Portfolio management: positions, watchlist and the alert engine."""
from __future__ import annotations

from datetime import datetime

from . import analysis, db, market
from .config import SIGNAL_BUY, SIGNAL_SELL

SEVERITY_ORDER = {"critical": 0, "high": 1, "warning": 2, "medium": 3, "info": 4}


def _analyze(symbol: str) -> dict | None:
    """Full analysis from cached candles (network only when cache is stale/missing)."""
    try:
        candles, _ = market.get_candles(symbol, days=300)
        return analysis.analyze_symbol(symbol, candles)
    except Exception:  # noqa: BLE001 - analysis must never break a scan
        return None


def _num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------- positions

def positions_overview() -> list[dict]:
    rows = db.query("SELECT * FROM positions WHERE status = 'OPEN' ORDER BY id")
    out: list[dict] = []
    for row in rows:
        payload = _analyze(row["symbol"])
        price = payload["price"] if payload else None
        quantity = int(row["quantity"] or 0)
        avg_cost = _num(row["avg_cost"]) or 0.0
        cost = quantity * avg_cost
        value = quantity * price if price else cost
        pnl = value - cost
        stop = _num(row["stop_loss"])
        take = _num(row["take_profit"])
        if not stop and payload:
            stop = payload["levels"].get("stop_loss")
        out.append(
            {
                **row,
                "price": price,
                "change_pct": payload.get("change_pct") if payload else None,
                "signal": payload["signal"] if payload else None,
                "score": payload["signal"]["score"] if payload else None,
                "value": round(value, 0),
                "cost": round(cost, 0),
                "pnl": round(pnl, 0),
                "pnl_pct": round(pnl / cost * 100, 2) if cost else None,
                "suggested_stop": payload["levels"].get("stop_loss") if payload else None,
                "stop_distance_pct": round((price - stop) / price * 100, 2) if (price and stop) else None,
                "target": take,
                "buy_zone": payload["levels"].get("buy_zone") if payload else [],
            }
        )
    return out


def portfolio_summary(positions: list[dict]) -> dict:
    settings = db.get_settings()
    equity = _num(settings.get("equity")) or 0.0
    market_value = sum(p["value"] or 0 for p in positions)
    cost = sum(p["cost"] or 0 for p in positions)
    pnl = market_value - cost
    return {
        "equity": equity,
        "cash": round(equity - cost, 0),
        "positions": len(positions),
        "market_value": round(market_value, 0),
        "cost": round(cost, 0),
        "pnl": round(pnl, 0),
        "pnl_pct": round(pnl / cost * 100, 2) if cost else 0.0,
        "allocation_pct": round(cost / equity * 100, 1) if equity else None,
    }


def create_position(data: dict) -> int:
    symbol = str(data.get("symbol") or "").strip().upper()
    if not symbol:
        raise ValueError("Thiếu mã cổ phiếu")
    quantity = int(_num(data.get("quantity")) or 0)
    avg_cost = _num(data.get("avg_cost"))
    if quantity <= 0 or not avg_cost or avg_cost <= 0:
        raise ValueError("Khối lượng và giá vốn phải lớn hơn 0")
    now = db.now_str()
    return db.execute(
        "INSERT INTO positions(symbol, quantity, avg_cost, buy_date, stop_loss, take_profit, note, status, created_at, updated_at) "
        "VALUES(?, ?, ?, ?, ?, ?, ?, 'OPEN', ?, ?)",
        (
            symbol,
            quantity,
            avg_cost,
            data.get("buy_date") or db.today_str(),
            _num(data.get("stop_loss")),
            _num(data.get("take_profit")),
            (data.get("note") or "").strip() or None,
            now,
            now,
        ),
    )


def update_position(position_id: int, data: dict) -> None:
    row = db.query_one("SELECT * FROM positions WHERE id = ?", (position_id,))
    if not row:
        raise ValueError("Không tìm thấy vị thế")
    db.execute(
        "UPDATE positions SET quantity = ?, avg_cost = ?, stop_loss = ?, take_profit = ?, note = ?, status = ?, updated_at = ? WHERE id = ?",
        (
            int(_num(data.get("quantity", row["quantity"])) or row["quantity"]),
            _num(data.get("avg_cost", row["avg_cost"])) or row["avg_cost"],
            _num(data.get("stop_loss", row["stop_loss"])),
            _num(data.get("take_profit", row["take_profit"])),
            (data.get("note", row["note"]) or None),
            data.get("status", row["status"] or "OPEN"),
            db.now_str(),
            position_id,
        ),
    )


def delete_position(position_id: int) -> None:
    db.execute("DELETE FROM positions WHERE id = ?", (position_id,))


# ------------------------------------------------------------- watchlist

def watchlist_rows() -> list[dict]:
    rows = db.query("SELECT * FROM watchlist ORDER BY id DESC")
    out: list[dict] = []
    for row in rows:
        payload = _analyze(row["symbol"])
        out.append(
            {
                **row,
                "price": payload["price"] if payload else None,
                "change_pct": payload.get("change_pct") if payload else None,
                "signal": payload["signal"] if payload else None,
                "buy_zone": payload["levels"].get("buy_zone") if payload else [],
                "stop_loss": payload["levels"].get("stop_loss") if payload else None,
            }
        )
    return out


def add_watch(data: dict) -> int:
    symbol = str(data.get("symbol") or "").strip().upper()
    if not symbol:
        raise ValueError("Thiếu mã cổ phiếu")
    return db.execute(
        "INSERT INTO watchlist(symbol, note, target_price, created_at) VALUES(?, ?, ?, ?) "
        "ON CONFLICT(symbol) DO UPDATE SET note = excluded.note, target_price = excluded.target_price",
        (symbol, (data.get("note") or "").strip() or None, _num(data.get("target_price")), db.now_str()),
    )


def remove_watch(watch_id: int) -> None:
    db.execute("DELETE FROM watchlist WHERE id = ?", (watch_id,))


# ----------------------------------------------------------------- alerts

def _upsert_alert(symbol: str, alert_type: str, severity: str, message: str, price: float | None) -> None:
    db.execute(
        "INSERT INTO alerts(symbol, type, severity, message, price, day, created_at, acknowledged) "
        "VALUES(?, ?, ?, ?, ?, ?, ?, 0) "
        "ON CONFLICT(symbol, type, day) DO UPDATE SET message = excluded.message, "
        "severity = excluded.severity, price = excluded.price, created_at = excluded.created_at",
        (symbol, alert_type, severity, message, price, db.today_str(), db.now_str()),
    )


def scan_alerts(force: bool = False) -> dict:
    """Scan positions + watchlist and raise alerts (buy/sell/stop-loss/target)."""
    settings = db.get_settings()
    interval_minutes = max(int(_num(settings.get("scan_minutes")) or 30), 1)
    last_scan = db.get_setting("last_scan_at")
    if not force and last_scan:
        try:
            elapsed = (datetime.now() - datetime.strptime(last_scan, "%Y-%m-%d %H:%M:%S")).total_seconds() / 60
            if elapsed < interval_minutes:
                return {"skipped": True, "reason": f"Bỏ qua: lần quét trước mới {int(elapsed)} phút trước", "created": 0}
        except (TypeError, ValueError):
            pass

    created = 0
    scanned = 0

    for row in db.query("SELECT * FROM positions WHERE status = 'OPEN'"):
        symbol = row["symbol"]
        payload = _analyze(symbol)
        scanned += 1
        if not payload:
            continue
        price = payload["price"]
        signal = payload["signal"]["code"]
        score = payload["signal"]["score"]
        avg_cost = _num(row["avg_cost"]) or 0.0
        stop = _num(row["stop_loss"]) or payload["levels"].get("stop_loss")
        take = _num(row["take_profit"])
        pnl_pct = (price - avg_cost) / avg_cost * 100 if avg_cost else 0.0

        if stop and price <= stop:
            _upsert_alert(symbol, "STOP_LOSS", "critical",
                          f"CẮT LỖ {symbol}: giá {price:,.0f} đã chạm cắt lỗ {stop:,.0f} ({pnl_pct:+.1f}%). Cân nhắc thoát vị thế.",
                          price)
            created += 1
        if take and price >= take:
            _upsert_alert(symbol, "TAKE_PROFIT", "medium",
                          f"CHỐT LỜI {symbol}: giá {price:,.0f} đạt mục tiêu {take:,.0f} ({pnl_pct:+.1f}%).",
                          price)
            created += 1
        if signal in {"SELL", "STRONG_SELL"}:
            _upsert_alert(symbol, "SELL_SIGNAL", "high",
                          f"TÍN HIỆU BÁN {symbol}: điểm tín hiệu {score:+.0f}, giá {price:,.0f}. Xem xét giảm tỷ trọng.",
                          price)
            created += 1
        elif signal in {"BUY", "STRONG_BUY"} and _profitable(price, avg_cost):
            _upsert_alert(symbol, "ADD_SIGNAL", "info",
                          f"TÍN HIỆU MUA {symbol}: điểm {score:+.0f}, giá {price:,.0f}. Cân nhắc gia tăng theo 1/2 Kelly.",
                          price)
            created += 1

        # trailing stop: drawdown from recent peak while in profit
        candles = db.load_candles(symbol, limit=30)
        if candles and avg_cost:
            peak = max(float(c["h"]) for c in candles[-20:])
            if price < peak * 0.92 and price > avg_cost:
                _upsert_alert(symbol, "TRAILING_STOP", "warning",
                              f"CHỐT LÃI CHỦ ĐỘNG {symbol}: giá {price:,.0f} giảm >8% từ đỉnh gần nhất {peak:,.0f}.",
                              price)
                created += 1

        # support break below strong support
        supports = [s for s in (payload.get("supports") or []) if s.get("touches", 0) >= 2]
        if supports:
            strongest = max(supports, key=lambda s: s["score"] or 0)
            if price < strongest["price"] and (price - strongest["price"]) / price > -0.03:
                _upsert_alert(symbol, "SUPPORT_BREAK", "warning",
                              f"THỦNG HỖ TRỢ {symbol}: giá {price:,.0f} dưới hỗ trợ {strongest['price']:,.0f} ({strongest['touches']} lần chạm).",
                              price)
                created += 1

    for row in db.query("SELECT * FROM watchlist"):
        symbol = row["symbol"]
        payload = _analyze(symbol)
        scanned += 1
        if not payload:
            continue
        price = payload["price"]
        signal = payload["signal"]["code"]
        score = payload["signal"]["score"]
        if signal in {"BUY", "STRONG_BUY"}:
            _upsert_alert(symbol, "BUY_SIGNAL", "medium",
                          f"TÍN HIỆU MUA {symbol}: điểm {score:+.0f}, giá {price:,.0f}. Vùng mua tham khảo "
                          f"{fmt_zone(payload['levels'].get('buy_zone'))}.",
                          price)
            created += 1
        if signal in {"SELL", "STRONG_SELL"}:
            _upsert_alert(symbol, "SELL_SIGNAL_WATCH", "info",
                          f"TÍN HIỆU BÁN {symbol} (đang theo dõi): điểm {score:+.0f}, giá {price:,.0f}.",
                          price)
            created += 1
        target = _num(row["target_price"])
        if target and price >= target:
            _upsert_alert(symbol, "WATCH_TARGET", "medium",
                          f"ĐẠT GIÁ MỤC TIÊU {symbol}: giá {price:,.0f} ≥ mục tiêu {target:,.0f}.",
                          price)
            created += 1

    db.set_setting("last_scan_at", db.now_str())
    return {"skipped": False, "created": created, "scanned": scanned}


def _profitable(price: float, avg_cost: float) -> bool:
    return bool(avg_cost) and price > avg_cost


def fmt_zone(zone: list | None) -> str:
    if not zone or len(zone) < 2 or not zone[0] or not zone[1]:
        return "theo Fibonacci"
    return f"{zone[0]:,.0f} – {zone[1]:,.0f}"


def alerts_list(limit: int = 100, include_ack: bool = False) -> list[dict]:
    where = "" if include_ack else "WHERE acknowledged = 0"
    return db.query(
        f"SELECT * FROM alerts {where} ORDER BY created_at DESC LIMIT ?",
        (limit,),
    )


def alerts_count() -> int:
    row = db.query_one("SELECT COUNT(*) AS n FROM alerts WHERE acknowledged = 0")
    return int(row["n"]) if row else 0


def ack_alert(alert_id: int) -> None:
    db.execute("UPDATE alerts SET acknowledged = 1 WHERE id = ?", (alert_id,))


def ack_all() -> None:
    db.execute("UPDATE alerts SET acknowledged = 1 WHERE acknowledged = 0")
