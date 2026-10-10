"""Derivatives analysis (VN30F Day Trading) based on Ed Thorp principles."""
from __future__ import annotations

import datetime
from . import indicators as ta
from . import vietcap

def _typical_price(h, l, c):
    return (h + l + c) / 3.0

def calc_daily_vwap(candles: list[dict]) -> list[float | None]:
    vwap_out = [None] * len(candles)
    cum_pv = 0.0
    cum_vol = 0.0
    last_date = None
    
    for i, c in enumerate(candles):
        # candles have 't': '2026-10-09T14:45:00+07:00'
        # Extract date string
        t = c["t"]
        current_date = t[:10] if "T" in t else t
        
        if current_date != last_date:
            cum_pv = 0.0
            cum_vol = 0.0
            last_date = current_date
            
        tp = _typical_price(c["h"], c["l"], c["c"])
        vol = c["v"]
        
        cum_pv += tp * vol
        cum_vol += vol
        
        if cum_vol > 0:
            vwap_out[i] = cum_pv / cum_vol
        else:
            vwap_out[i] = tp
            
    return vwap_out


def calc_pivot_points(daily_candles: list[dict]) -> dict:
    if len(daily_candles) < 2:
        return {}
    # Use yesterday's candle
    y = daily_candles[-2]
    h, l, c = y["h"], y["l"], y["c"]
    p = (h + l + c) / 3
    r1 = p * 2 - l
    s1 = p * 2 - h
    r2 = p + (h - l)
    s2 = p - (h - l)
    
    # Today's pivot points
    return {
        "P": p,
        "R1": r1,
        "R2": r2,
        "S1": s1,
        "S2": s2
    }


def _time_str_to_minutes(t_str: str) -> int:
    """Extract 'HH:MM' from '2026-10-09T09:15:00+07:00' and convert to minutes from midnight."""
    if "T" not in t_str: return 0
    time_part = t_str.split("T")[1][:5]
    h, m = map(int, time_part.split(":"))
    return h * 60 + m


def analyze_derivatives(margin: float = 100000000, max_loss_pct: float = 1.0) -> dict:
    # 1. Fetch data
    try:
        candles_5m = vietcap.fetch_history("VN30F1M", count=150, timeframe="FIVE_MINUTES")
        daily_candles = vietcap.fetch_history("VN30F1M", count=10, timeframe="ONE_DAY")
    except Exception as e:
        raise ValueError(f"Không lấy được dữ liệu phái sinh: {e}")
        
    if not candles_5m or not daily_candles:
        raise ValueError("Thiếu dữ liệu để phân tích")
        
    # 2. Indicators
    closes_5m = [c["c"] for c in candles_5m]
    vwap_5m = calc_daily_vwap(candles_5m)
    rsi_5m = ta.rsi(closes_5m, period=9)
    pivots = calc_pivot_points(daily_candles)
    
    # Current values
    curr_c = candles_5m[-1]
    curr_vwap = vwap_5m[-1]
    curr_rsi = rsi_5m[-1]
    
    # Look back for "price completely above/below VWAP in first 30 mins" 
    # Just check if recent 3-6 candles were above/below VWAP
    is_above_vwap = True
    is_below_vwap = True
    for i in range(max(0, len(candles_5m) - 6), len(candles_5m)):
        c, v = closes_5m[i], vwap_5m[i]
        if c and v:
            if c < v: is_above_vwap = False
            if c > v: is_below_vwap = False
            
    # Check time (avoid 9:00-9:15 and 14:15-14:30)
    current_time = _time_str_to_minutes(curr_c["t"])
    in_danger_zone = (9*60 <= current_time <= 9*60+15) or (14*60+15 <= current_time <= 14*60+30)
    
    # 3. Setup Triggers
    trend_long = False
    trend_short = False
    mean_long = False
    mean_short = False
    
    # Trend Following Rules
    if is_above_vwap and curr_c["c"] <= curr_vwap * 1.001 and curr_rsi and 40 <= curr_rsi <= 50:
        trend_long = True
    if is_below_vwap and curr_c["c"] >= curr_vwap * 0.999 and curr_rsi and 50 <= curr_rsi <= 60:
        trend_short = True
        
    # Mean Reversion Rules (Climax)
    if pivots.get("S2") and curr_c["c"] <= pivots["S2"] * 1.002 and curr_rsi and curr_rsi < 25:
        mean_long = True
    if pivots.get("R2") and curr_c["c"] >= pivots["R2"] * 0.998 and curr_rsi and curr_rsi > 75:
        mean_short = True
        
    signal = "NEUTRAL"
    setup_name = "Không có"
    entry_price = curr_c["c"]
    stop_loss = 0
    target = 0
    
    if mean_long:
        signal = "LONG"
        setup_name = "Đảo chiều cực đại (S2 / Quá bán)"
        stop_loss = entry_price - 2.0
        target = pivots.get("P", entry_price + 5)
    elif mean_short:
        signal = "SHORT"
        setup_name = "Đảo chiều cực đại (R2 / Quá mua)"
        stop_loss = entry_price + 2.0
        target = pivots.get("P", entry_price - 5)
    elif trend_long:
        signal = "LONG"
        setup_name = "Thuận xu hướng (Kéo về VWAP)"
        stop_loss = entry_price - 1.5
        target = pivots.get("R1", entry_price + 5)
    elif trend_short:
        signal = "SHORT"
        setup_name = "Thuận xu hướng (Kéo về VWAP)"
        stop_loss = entry_price + 1.5
        target = pivots.get("S1", entry_price - 5)
        
    # Risk Management (Fractional Kelly equivalent logic)
    # VN30F multiplier is 100,000 VND / point
    contract_multiplier = 100000 
    max_loss_vnd = margin * (max_loss_pct / 100.0)
    loss_points = abs(entry_price - stop_loss) if signal != "NEUTRAL" else 2.0
    loss_vnd_per_contract = loss_points * contract_multiplier
    
    max_contracts = 0
    if loss_vnd_per_contract > 0:
        max_contracts = int(max_loss_vnd // loss_vnd_per_contract)
        
    return {
        "symbol": "VN30F1M",
        "timestamp": curr_c["t"],
        "price": curr_c["c"],
        "vwap": round(curr_vwap, 2) if curr_vwap else None,
        "rsi": round(curr_rsi, 2) if curr_rsi else None,
        "pivots": {k: round(v, 2) for k, v in pivots.items()},
        "in_danger_zone": in_danger_zone,
        "signal": signal,
        "setup_name": setup_name,
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "target": target,
        "risk_reward": round(abs(target - entry_price) / loss_points, 2) if signal != "NEUTRAL" and loss_points > 0 else 0,
        "max_contracts": max_contracts,
        "max_loss_vnd": max_loss_vnd
    }

