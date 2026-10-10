"""Phân tích kỹ thuật theo phương pháp CANSLIM."""
from __future__ import annotations

from typing import Any, Optional

from . import indicators as ta

def _is_distribution_day(candles: list[dict], i: int) -> bool:
    if i < 1:
        return False
    prev_close = float(candles[i-1]["c"])
    curr_close = float(candles[i]["c"])
    prev_vol = float(candles[i-1].get("v") or 0)
    curr_vol = float(candles[i].get("v") or 0)
    
    # Phân phối: Giá giảm >= 0.2% và Khối lượng cao hơn phiên trước
    return (curr_close < prev_close * 0.998) and (curr_vol > prev_vol)


def analyze_market_direction(vnindex_candles: list[dict]) -> dict:
    if len(vnindex_candles) < 200:
        return {"status": "KHÔNG ĐỦ DỮ LIỆU", "distribution_days": 0, "passed": True}
        
    closes = [float(c["c"]) for c in vnindex_candles]
    current_price = closes[-1]
    sma50 = ta.sma(closes, 50)
    sma200 = ta.sma(closes, 200)
    ma50 = ta.last(sma50) or current_price
    ma200 = ta.last(sma200) or current_price
    
    is_uptrend = (current_price > ma50) and (current_price > ma200)
    
    # Đếm ngày phân phối trong 25 phiên gần nhất (khoảng 5 tuần)
    dist_days = 0
    recent_candles = vnindex_candles[-26:]
    for i in range(1, len(recent_candles)):
        if _is_distribution_day(recent_candles, i):
            dist_days += 1
            
    passed = is_uptrend and (dist_days < 5)
    
    status = "UPTREND MẠNH"
    if not is_uptrend:
        status = "DOWNTREND / TÍCH LŨY"
    elif dist_days >= 4:
        status = "UPTREND DƯỚI ÁP LỰC BÁN"
        
    return {
        "status": status,
        "is_uptrend": is_uptrend,
        "distribution_days": dist_days,
        "passed": passed,
        "ma50": ma50,
        "ma200": ma200,
        "current": current_price
    }


def _detect_patterns(closes: list[float], highs: list[float], lows: list[float]) -> dict:
    # Logic đơn giản nhận diện mẫu hình (Base)
    # Lấy 30-40 phiên gần nhất
    lookback = min(len(closes), 40)
    recent_highs = highs[-lookback:-1]
    recent_lows = lows[-lookback:-1]
    
    if not recent_highs:
        return {"name": "Không rõ ràng", "pivot": closes[-1]}
        
    highest_price = max(recent_highs)
    lowest_price = min(recent_lows)
    current_price = closes[-1]
    
    # Tính độ sâu điều chỉnh
    depth = (highest_price - lowest_price) / highest_price * 100
    
    pattern_name = "Không đạt chuẩn"
    pivot = highest_price
    
    if 5 <= depth <= 15:
        pattern_name = "Nền giá phẳng (Flat Base)"
    elif 15 < depth <= 35:
        pattern_name = "Cốc tay cầm / VCP"
        # Với Cốc tay cầm, giá hiện tại phải tiệm cận đỉnh cũ (cách < 10%)
        if (highest_price - current_price) / highest_price * 100 < 10:
            pattern_name = "Cốc tay cầm (Handle)"
            pivot = max(highs[-10:-1]) if len(highs) >= 10 else highest_price
    
    return {
        "name": pattern_name,
        "pivot": pivot,
        "depth_pct": round(depth, 1)
    }


def analyze_canslim(
    symbol: str, 
    candles: list[dict], 
    vnindex_candles: list[dict]
) -> dict:
    if len(candles) < 60:
        raise ValueError(f"Không đủ dữ liệu cho {symbol}")
        
    closes = [float(c["c"]) for c in candles]
    highs = [float(c["h"]) for c in candles]
    lows = [float(c["l"]) for c in candles]
    volumes = [float(c.get("v") or 0) for c in candles]
    
    current_price = closes[-1]
    current_vol = volumes[-1]
    
    v20_series = ta.sma(volumes, 20)
    v20 = ta.last(v20_series) or 0
    
    # 1. Chữ M - Market
    market_eval = analyze_market_direction(vnindex_candles)
    
    # 2. Mẫu hình & Pivot
    pattern = _detect_patterns(closes, highs, lows)
    pivot = pattern["pivot"]
    
    # 3. Điểm mua chuẩn
    is_breakout = current_price >= pivot * 0.99
    vol_breakout = current_vol >= (v20 * 1.5) if v20 > 0 else False
    
    buy_zone_low = pivot
    buy_zone_high = pivot * 1.05
    
    in_buy_zone = (buy_zone_low * 0.99 <= current_price <= buy_zone_high)
    is_fomo = current_price > buy_zone_high
    
    buy_trigger = is_breakout and vol_breakout and in_buy_zone
    
    # 4. Quản trị rủi ro
    stop_loss = pivot * 0.925 # -7.5%
    target_profit = pivot * 1.25 # +25%
    
    # Đánh giá tổng quan
    passed = market_eval["passed"] and pattern["name"] != "Không đạt chuẩn" and buy_trigger
    
    status = "CHỜ BỨT PHÁ"
    if not market_eval["passed"]:
        status = "THỊ TRƯỜNG XẤU"
    elif is_fomo:
        status = "QUÁ ĐIỂM MUA (FOMO)"
    elif buy_trigger:
        status = "ĐIỂM MUA CHUẨN (BREAKOUT)"
        
    return {
        "symbol": symbol.upper(),
        "market": market_eval,
        "pattern": pattern,
        "pivot": round(pivot, 2) if pivot else None,
        "current_price": current_price,
        "current_vol": current_vol,
        "v20": round(v20, 0),
        "is_breakout": is_breakout,
        "vol_breakout": vol_breakout,
        "buy_zone": [round(buy_zone_low, 2), round(buy_zone_high, 2)],
        "in_buy_zone": in_buy_zone,
        "is_fomo": is_fomo,
        "buy_trigger": buy_trigger,
        "stop_loss": round(stop_loss, 2),
        "target_profit": round(target_profit, 2),
        "status": status,
        "passed": passed
    }

