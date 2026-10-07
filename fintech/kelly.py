"""Capital management with the Kelly criterion (Edward Thorp, 1/2 Kelly).

Thorp's practical guidance:
  - Full Kelly maximizes long-term compounding but has deep drawdowns.
  - Fractional Kelly (half-Kelly) trades ~25% of the growth rate for a much
    smoother equity curve and far smaller drawdowns.

f* = p - q / b   (p = win probability, q = 1 - p, b = net payoff ratio)
Position amount  = equity * f*_used
Recommended qty  = min(kelly qty, risk-based qty, position-cap qty)
"""
from __future__ import annotations


def kelly_fraction(win_prob: float, payoff: float) -> float:
    """Full Kelly fraction of capital, floored at 0."""
    try:
        p = min(max(float(win_prob), 0.0), 1.0)
        b = max(float(payoff), 1e-9)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, p - (1.0 - p) / b)


def half_kelly(win_prob: float, payoff: float) -> float:
    """1/2 Kelly — Edward Thorp's recommended safety fraction."""
    return kelly_fraction(win_prob, payoff) / 2.0


def position_size(equity: float, fraction: float, entry: float, stop: float, *,
                  risk_pct: float = 2.0, max_position_pct: float = 20.0, lot: int = 100) -> dict:
    """Translate a capital fraction into an executable order size (VND)."""
    equity = max(float(equity or 0), 0.0)
    entry = float(entry or 0)
    stop = float(stop or 0)
    lot = max(int(lot or 100), 1)
    if equity <= 0 or entry <= 0 or fraction <= 0:
        return {
            "amount": 0.0, "quantity": 0, "risk_amount": 0.0,
            "risk_per_share": None, "kelly_amount": 0.0,
            "cap_amount": equity * max_position_pct / 100.0,
        }
    kelly_amount = equity * fraction
    cap_amount = equity * max_position_pct / 100.0
    risk_budget = equity * risk_pct / 100.0
    risk_per_share = max(entry - stop, entry * 0.005)
    qty_kelly = kelly_amount / entry
    qty_risk = risk_budget / risk_per_share
    qty_cap = cap_amount / entry
    qty = int(min(qty_kelly, qty_risk, qty_cap) // lot * lot)
    amount = qty * entry
    return {
        "amount": round(amount, 0),
        "quantity": qty,
        "risk_amount": round(qty * risk_per_share, 0),
        "risk_per_share": round(risk_per_share, 1),
        "kelly_amount": round(kelly_amount, 0),
        "risk_budget": round(risk_budget, 0),
        "cap_amount": round(cap_amount, 0),
        "qty_kelly": int(qty_kelly // lot * lot),
        "qty_risk": int(qty_risk // lot * lot),
        "qty_cap": int(qty_cap // lot * lot),
    }


def recommendation(win_prob: float, payoff: float, entry: float, stop: float, equity: float, *,
                   mode: str = "half", risk_pct: float = 2.0, max_position_pct: float = 20.0,
                   lot: int = 100) -> dict:
    """Full recommendation payload consumed by the UI."""
    full = kelly_fraction(win_prob, payoff)
    half = full / 2.0
    used = half if mode != "full" else full
    sizing = position_size(equity, used, entry, stop, risk_pct=risk_pct,
                           max_position_pct=max_position_pct, lot=lot)

    notes: list[str] = []
    if full <= 0:
        notes.append("Kelly ≤ 0: xác suất thắng không đủ bù rủi ro — không nên vào lệnh theo mô hình này.")
    if mode != "full":
        notes.append("Đang dùng 1/2 Kelly: tăng trưởng chậm hơn ~25% so với Kelly đầy đủ nhưng drawdown giảm mạnh (khuyến nghị của Edward Thorp).")
    if sizing["quantity"] == 0 and used > 0:
        notes.append("Khối lượng tính ra dưới 1 lô — cân nhắc bỏ qua hoặc tăng vốn.")
    notes.append("Luôn ưu tiên tỷ lệ rủi ro mỗi lệnh ≤ 2% vốn; Kelly chỉ là giới hạn trên của phân bổ.")

    return {
        "win_prob": round(min(max(float(win_prob), 0.0), 1.0) * 100, 1),
        "payoff": round(float(payoff), 2),
        "kelly_full_pct": round(full * 100, 2),
        "kelly_half_pct": round(half * 100, 2),
        "used_fraction_pct": round(used * 100, 2),
        "mode": mode,
        "equity": round(float(equity or 0), 0),
        "entry": round(float(entry or 0), 1),
        "stop": round(float(stop or 0), 1),
        **sizing,
        "notes": notes,
    }
