"""Trading journal (sổ giao dịch): user trade log + FIFO realized P&L.

Each trade row: trade_date, symbol, side (BUY/SELL), quantity, price, fee.
Realized profit/loss is computed per SELL with first-in-first-out matching
against that symbol's earlier BUY lots; remaining open lots form the open
position (vốn đang nắm giữ).
"""
from __future__ import annotations

from datetime import datetime

from . import db

_SIDES = {"BUY": "Mua", "SELL": "Bán"}


def _num(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _valid_date(value: str) -> str | None:
    text = str(value or "").strip()
    try:
        return datetime.strptime(text, "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        return None


def validate_trade(body: dict) -> dict:
    symbol = str(body.get("symbol") or "").strip().upper()
    side = str(body.get("side") or "").strip().upper()
    trade_date = _valid_date(body.get("trade_date") or body.get("date"))
    quantity = _num(body.get("quantity"))
    price = _num(body.get("price"))
    fee = _num(body.get("fee"), 0.0) or 0.0
    note = str(body.get("note") or "").strip()[:200]

    if not symbol:
        raise ValueError("Thiếu mã cổ phiếu")
    if side not in _SIDES:
        raise ValueError("Hướng lệnh phải là BUY (mua) hoặc SELL (bán)")
    if trade_date is None:
        raise ValueError("Ngày giao dịch không hợp lệ (định dạng YYYY-MM-DD)")
    if not quantity or quantity <= 0:
        raise ValueError("Khối lượng phải lớn hơn 0")
    if not price or price <= 0:
        raise ValueError("Giá phải lớn hơn 0")
    if fee < 0:
        raise ValueError("Phí không thể âm")
    return {
        "symbol": symbol,
        "side": side,
        "trade_date": trade_date,
        "quantity": quantity,
        "price": price,
        "fee": fee,
        "note": note,
    }


def add_trade(user_id: str, body: dict) -> int:
    fields = validate_trade(body)
    fields["user_id"] = str(user_id)
    fields["created_at"] = db.now_str()
    return db.trade_create(fields)


def delete_trade(trade_id: int, user_id: str) -> bool:
    row = db.trade_latest(trade_id)
    if row is None or str(row.get("user_id")) != str(user_id):
        return False
    db.trade_delete(trade_id)
    return True


def list_trades(user_id: str) -> list[dict]:
    rows = db.trades_for(user_id)
    for row in rows:
        row["side_label"] = _SIDES.get(row.get("side") or "", row.get("side"))
        row["value"] = round((row.get("quantity") or 0) * (row.get("price") or 0), 0)
    return rows


def summary(trades: list[dict]) -> dict:
    """FIFO realized P&L per symbol + portfolio-level aggregates."""
    realized_by_id: dict[int, float] = {}
    realized_total = 0.0

    by_symbol: dict[str, list[dict]] = {}
    for row in trades:
        by_symbol.setdefault(row.get("symbol") or "", []).append(row)

    open_exact: dict[str, dict] = {}
    for symbol, rows in by_symbol.items():
        rows.sort(key=lambda r: (r.get("trade_date") or "", r.get("id") or 0))
        lots: list[list] = []  # [quantity, cost_per_share (price + fee)]
        for row in rows:
            qty = float(row.get("quantity") or 0)
            price = float(row.get("price") or 0)
            fee_per_share = float(row.get("fee") or 0) / max(qty, 1)
            if row.get("side") == "BUY":
                lots.append([qty, price + fee_per_share])
            else:
                pnl = -float(row.get("fee") or 0)
                remaining = qty
                while remaining > 1e-9 and lots:
                    lot = lots[0]
                    take = min(remaining, lot[0])
                    pnl += take * (price - lot[1])
                    lot[0] -= take
                    remaining -= take
                    if lot[0] <= 1e-9:
                        lots.pop(0)
                realized_by_id[row.get("id")] = round(pnl, 0)
                realized_total += pnl
        if lots:
            quantity = sum(lot[0] for lot in lots)
            cost = sum(lot[0] * lot[1] for lot in lots)
            open_exact[symbol] = {
                "symbol": symbol,
                "quantity": round(quantity, 0),
                "cost": round(cost, 0),
                "avg_cost": round(cost / quantity, 2) if quantity else None,
            }

    wins = sum(1 for value in realized_by_id.values() if value > 0)
    losses = sum(1 for value in realized_by_id.values() if value < 0)
    sells = sum(1 for row in trades if row.get("side") == "SELL")
    closed = wins + losses
    return {
        "trades_count": len(trades),
        "buy_count": sum(1 for row in trades if row.get("side") == "BUY"),
        "sell_count": sells,
        "realized_pnl": round(realized_total, 0),
        "closed_trades": closed,
        "win_trades": wins,
        "loss_trades": losses,
        "win_rate": round(wins / closed * 100, 1) if closed else None,
        "open_cost": round(sum(v["cost"] for v in open_exact.values()), 0),
        "open_positions": sorted(open_exact.values(), key=lambda v: -(v["cost"])),
        "realized_by_id": realized_by_id,
    }
