"""Backtesting engines for CANSLIM, Trend Following, and Derivatives."""
from __future__ import annotations

import datetime
from . import market, vietcap
from . import indicators as ta
from . import canslim, trend_following, derivatives

def _find_index(candles: list[dict], target_date: str, default: int) -> int:
    for i, c in enumerate(candles):
        if c["t"][:10] >= target_date:
            return i
    return default


def run_canslim_backtest(symbol: str, start_date: str, end_date: str) -> dict:
    candles, _ = market.get_candles(symbol, days=2000, cache_hours=6)
    vn_candles, _ = market.get_candles("VNINDEX", days=2000, cache_hours=6)
    
    # Align dates
    if not candles: return {"trades": [], "summary": {}}
    
    start_idx = max(60, _find_index(candles, start_date, 60))
    end_idx = _find_index(candles, end_date, len(candles) - 1)
    
    trades = []
    position = None
    
    # Precalculate for VNINDEX
    vn_closes = [c["c"] for c in vn_candles]
    vn_sma50 = ta.sma(vn_closes, 50)
    vn_sma200 = ta.sma(vn_closes, 200)
    
    # Precalculate for symbol
    closes = [c["c"] for c in candles]
    highs = [c["h"] for c in candles]
    lows = [c["l"] for c in candles]
    vols = [c["v"] for c in candles]
    v20 = ta.sma(vols, 20)
    
    # Helper for vnindex sync
    def get_vn_idx(date_str):
        for j in range(len(vn_candles)-1, -1, -1):
            if vn_candles[j]["t"][:10] <= date_str:
                return j
        return 0

    for i in range(start_idx, end_idx + 1):
        c = candles[i]
        date_str = c["t"][:10]
        
        if position:
            # Check exit
            h, l = c["h"], c["l"]
            stop_loss = position["stop_loss"]
            target = position["target"]
            
            exit_price = None
            reason = ""
            
            if l <= stop_loss:
                exit_price = stop_loss
                reason = "Cắt lỗ"
            elif h >= target:
                exit_price = target
                reason = "Chốt lời"
            
            if exit_price:
                pnl_pct = (exit_price - position["entry_price"]) / position["entry_price"] * 100
                trades.append({
                    "entry_date": position["entry_date"],
                    "entry_price": position["entry_price"],
                    "exit_date": date_str,
                    "exit_price": exit_price,
                    "pnl_pct": round(pnl_pct, 2),
                    "reason": reason
                })
                position = None
            continue
            
        # Check entry
        vn_idx = get_vn_idx(date_str)
        if vn_idx < 200: continue
        
        # We need to simulate the exact CANSLIM logic at day i.
        # It's safer to call the analyze_canslim function directly but we must mock the arrays.
        # To make it fast enough for a few hundred days, slicing in Python is OK (O(N) slice, total O(N^2)).
        # N=1000 => 1M ops, which takes <0.1s in Python.
        
        vn_sub = vn_candles[:vn_idx+1]
        sym_sub = candles[:i+1]
        
        try:
            res = canslim.analyze_canslim(symbol, sym_sub, vn_sub)
            if res["passed"] and res["buy_trigger"]:
                position = {
                    "entry_date": date_str,
                    "entry_price": c["c"],
                    "stop_loss": res["stop_loss"],
                    "target": res["target_profit"]
                }
        except Exception:
            pass

    return _summarize(trades)


def run_trendfollowing_backtest(symbol: str, start_date: str, end_date: str) -> dict:
    candles, _ = market.get_candles(symbol, days=2000, cache_hours=6)
    if not candles: return {"trades": [], "summary": {}}
    
    start_idx = max(200, _find_index(candles, start_date, 200))
    end_idx = _find_index(candles, end_date, len(candles) - 1)
    
    trades = []
    position = None
    
    # Precalculate SMAs
    closes = [c["c"] for c in candles]
    ema20 = ta.ema(closes, 20)
    ema50 = ta.ema(closes, 50)
    
    for i in range(start_idx, end_idx + 1):
        c = candles[i]
        date_str = c["t"][:10]
        
        if position:
            # Trailing stop logic: close < EMA50
            e50 = ema50[i-1] or ema50[i]
            if e50 and c["c"] < e50:
                pnl_pct = (c["c"] - position["entry_price"]) / position["entry_price"] * 100
                trades.append({
                    "entry_date": position["entry_date"],
                    "entry_price": position["entry_price"],
                    "exit_date": date_str,
                    "exit_price": c["c"],
                    "pnl_pct": round(pnl_pct, 2),
                    "reason": "Trailing Stop (Thủng EMA50)"
                })
                position = None
            continue
            
        sym_sub = candles[:i+1]
        try:
            res = trend_following.analyze_trend_following(symbol, sym_sub)
            if res["step2_buy_trigger"]:
                position = {
                    "entry_date": date_str,
                    "entry_price": c["c"]
                }
        except Exception:
            pass

    return _summarize(trades)


def run_derivatives_backtest(start_date: str, end_date: str) -> dict:
    # 5000 candles is ~5 months of 5M data
    try:
        candles_5m = vietcap.fetch_history("VN30F1M", count=5000, timeframe="FIVE_MINUTES")
        daily_candles = vietcap.fetch_history("VN30F1M", count=200, timeframe="ONE_DAY")
    except Exception:
        return {"trades": [], "summary": {}}
        
    start_idx = _find_index(candles_5m, start_date, 0)
    end_idx = _find_index(candles_5m, end_date, len(candles_5m) - 1)
    
    vwap_5m = derivatives.calc_daily_vwap(candles_5m)
    closes = [c["c"] for c in candles_5m]
    rsi_5m = ta.rsi(closes, 9)
    
    # Pre-build daily pivots dict { "YYYY-MM-DD": pivots }
    pivots_by_date = {}
    for i in range(1, len(daily_candles)):
        today_date = daily_candles[i]["t"][:10]
        y = daily_candles[i-1]
        p = (y["h"] + y["l"] + y["c"]) / 3
        pivots_by_date[today_date] = {
            "P": p,
            "R1": p * 2 - y["l"],
            "S1": p * 2 - y["h"],
            "R2": p + (y["h"] - y["l"]),
            "S2": p - (y["h"] - y["l"])
        }
        
    trades = []
    position = None
    losses_today = 0
    current_day = ""
    
    for i in range(start_idx, end_idx + 1):
        if i < 6: continue
        c = candles_5m[i]
        date_str = c["t"][:10]
        
        if date_str != current_day:
            losses_today = 0
            current_day = date_str
            if position:
                # Force close overnight
                pnl = (c["o"] - position["entry_price"]) if position["type"] == "LONG" else (position["entry_price"] - c["o"])
                trades.append({
                    "entry_date": position["entry_date"],
                    "entry_price": position["entry_price"],
                    "type": position["type"],
                    "exit_date": c["t"],
                    "exit_price": c["o"],
                    "pnl": round(pnl, 2),
                    "reason": "Đóng qua đêm"
                })
                position = None
                
        current_time = derivatives._time_str_to_minutes(c["t"])
        end_of_day = (current_time >= 14 * 60 + 45)
        
        if position:
            h, l = c["h"], c["l"]
            sl = position["stop_loss"]
            tp = position["target"]
            
            exit_price = None
            reason = ""
            
            if position["type"] == "LONG":
                if l <= sl: exit_price, reason = sl, "Cắt lỗ"
                elif h >= tp: exit_price, reason = tp, "Chốt lời"
                elif end_of_day: exit_price, reason = c["c"], "Đóng cuối phiên"
            else:
                if h >= sl: exit_price, reason = sl, "Cắt lỗ"
                elif l <= tp: exit_price, reason = tp, "Chốt lời"
                elif end_of_day: exit_price, reason = c["c"], "Đóng cuối phiên"
                
            if exit_price is not None:
                pnl = (exit_price - position["entry_price"]) if position["type"] == "LONG" else (position["entry_price"] - exit_price)
                if pnl < 0: losses_today += 1
                trades.append({
                    "entry_date": position["entry_date"],
                    "entry_price": position["entry_price"],
                    "type": position["type"],
                    "exit_date": c["t"],
                    "exit_price": exit_price,
                    "pnl": round(pnl, 2),
                    "reason": reason
                })
                position = None
            continue
            
        # Check Entry
        if end_of_day or losses_today >= 2:
            continue
            
        in_danger_zone = (9*60 <= current_time <= 9*60+15) or (14*60+15 <= current_time <= 14*60+30)
        if in_danger_zone:
            continue
            
        curr_c = c["c"]
        curr_vwap = vwap_5m[i]
        curr_rsi = rsi_5m[i]
        pivs = pivots_by_date.get(date_str, {})
        
        is_above_vwap = all(closes[j] > vwap_5m[j] for j in range(i-3, i) if vwap_5m[j])
        is_below_vwap = all(closes[j] < vwap_5m[j] for j in range(i-3, i) if vwap_5m[j])
        
        trend_long = is_above_vwap and curr_c <= curr_vwap * 1.001 and curr_rsi and 40 <= curr_rsi <= 50
        trend_short = is_below_vwap and curr_c >= curr_vwap * 0.999 and curr_rsi and 50 <= curr_rsi <= 60
        mean_long = pivs.get("S2") and curr_c <= pivs["S2"] * 1.002 and curr_rsi and curr_rsi < 25
        mean_short = pivs.get("R2") and curr_c >= pivs["R2"] * 0.998 and curr_rsi and curr_rsi > 75
        
        if mean_long or trend_long:
            sl = curr_c - (2.0 if mean_long else 1.5)
            tp = pivs.get("P" if mean_long else "R1", curr_c + 5)
            position = {"type": "LONG", "entry_date": c["t"], "entry_price": curr_c, "stop_loss": sl, "target": tp}
        elif mean_short or trend_short:
            sl = curr_c + (2.0 if mean_short else 1.5)
            tp = pivs.get("P" if mean_short else "S1", curr_c - 5)
            position = {"type": "SHORT", "entry_date": c["t"], "entry_price": curr_c, "stop_loss": sl, "target": tp}
            
    return _summarize(trades, is_deriv=True)


def _summarize(trades: list[dict], is_deriv: bool = False) -> dict:
    if not trades:
        return {"trades": [], "summary": {"total": 0}}
        
    wins = [t for t in trades if (t.get("pnl", 0) > 0) or (t.get("pnl_pct", 0) > 0)]
    losses = [t for t in trades if (t.get("pnl", 0) <= 0) and (t.get("pnl_pct", 0) <= 0)]
    
    if is_deriv:
        total_pnl = sum(t["pnl"] for t in trades)
        max_loss = min([t["pnl"] for t in losses] + [0])
    else:
        total_pnl = sum(t["pnl_pct"] for t in trades)
        max_loss = min([t["pnl_pct"] for t in losses] + [0])
        
    win_rate = len(wins) / len(trades) * 100
    
    return {
        "trades": trades,
        "summary": {
            "total": len(trades),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate_pct": round(win_rate, 2),
            "total_return": round(total_pnl, 2),
            "max_loss": round(max_loss, 2)
        }
    }

