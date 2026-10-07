"""Technical analysis engine.

Components:
  - Fibonacci retracement / extension analysis with swing anchoring
  - Classic pivot points (daily / weekly / monthly)
  - Support & resistance clustering from swing points
  - Composite buy/sell scoring (trend, momentum, levels, volume, pivot)
  - Signal backtesting (for win-rate & payoff used by Kelly sizing)
  - Actionable buy/sell price levels (diem mua / diem ban)
"""
from __future__ import annotations

from datetime import datetime

from . import indicators as ta
from .config import (
    SIGNAL_BUY,
    SIGNAL_META,
    SIGNAL_SELL,
    SIGNAL_STRONG_BUY,
    SIGNAL_STRONG_SELL,
)

FIB_RATIOS = (0.236, 0.382, 0.5, 0.618, 0.786)
FIB_EXTENSIONS = (1.272, 1.618)


def _r(value, digits=1):
    if value is None:
        return None
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def _date_of(candle: dict) -> str:
    return str(candle.get("t") or "")


# ------------------------------------------------------------------ bundle

def compute_indicator_bundle(candles: list[dict]) -> dict:
    closes = [float(c["c"]) for c in candles]
    macd_line, macd_signal, macd_hist = ta.macd(closes)
    bb_upper, bb_mid, bb_lower = ta.bollinger(closes)
    return {
        "closes": closes,
        "ma20": ta.sma(closes, 20),
        "ma50": ta.sma(closes, 50),
        "ma200": ta.sma(closes, 200),
        "rsi": ta.rsi(closes, 14),
        "macd_line": macd_line,
        "macd_signal": macd_signal,
        "macd_hist": macd_hist,
        "atr": ta.atr(candles, 14),
        "vol_ma20": ta.volume_sma(candles, 20),
        "bb_upper": bb_upper,
        "bb_mid": bb_mid,
        "bb_lower": bb_lower,
    }


# --------------------------------------------------------------- fibonacci

def fib_analysis(candles: list[dict], lookback: int = 160) -> dict:
    """Swing-anchored Fibonacci retracement levels (ho tro / khang cu Fibo)."""
    if len(candles) < 40:
        return {"direction": None, "levels": [], "extensions": [], "level_map": {}, "ext_map": {}}
    window_start = max(0, len(candles) - lookback)
    window = candles[window_start:]
    highs = [float(c["h"]) for c in window]
    lows = [float(c["l"]) for c in window]
    hi_rel = max(range(len(highs)), key=lambda i: highs[i])
    lo_rel = min(range(len(lows)), key=lambda i: lows[i])
    hi_price = highs[hi_rel]
    lo_price = lows[lo_rel]
    last_close = float(candles[-1]["c"])
    if hi_price <= lo_price:
        return {"direction": None, "levels": [], "extensions": [], "level_map": {}, "ext_map": {}}
    rng = hi_price - lo_price
    uptrend = lo_rel < hi_rel  # day tang: tu day len dinh

    levels = []
    level_map: dict[float, float] = {}
    for ratio in FIB_RATIOS:
        price = hi_price - rng * ratio if uptrend else lo_price + rng * ratio
        level_map[ratio] = price
        levels.append({"ratio": ratio, "price": _r(price)})

    ext_map: dict[float, float] = {}
    extensions = []
    for ratio in FIB_EXTENSIONS:
        price = lo_price + rng * ratio if uptrend else hi_price - rng * ratio
        ext_map[ratio] = price
        extensions.append({"ratio": ratio, "price": _r(price)})

    golden = sorted([level_map[0.5], level_map[0.618]])
    supports = [p for p in level_map.values() if p <= last_close]
    resistances = [p for p in level_map.values() if p >= last_close]
    nearest_support = max(supports) if supports else None
    nearest_resistance = min(resistances) if resistances else None

    if uptrend:
        retracement = (hi_price - last_close) / rng
    else:
        retracement = (last_close - lo_price) / rng

    return {
        "direction": "UP" if uptrend else "DOWN",
        "lookback": len(window),
        "anchor_low": {"price": _r(lo_price), "date": _date_of(window[lo_rel])},
        "anchor_high": {"price": _r(hi_price), "date": _date_of(window[hi_rel])},
        "range": _r(rng),
        "levels": levels,
        "extensions": extensions,
        "level_map": level_map,
        "ext_map": ext_map,
        "golden_zone": [_r(golden[0]), _r(golden[1])],
        "nearest_support": _r(nearest_support),
        "nearest_resistance": _r(nearest_resistance),
        "retracement_pct": _r(retracement * 100, 2),
        "in_golden_zone": bool(golden[0] <= last_close <= golden[1]),
    }


# ------------------------------------------------------------------ pivots

def classic_pivot(high: float, low: float, close: float) -> dict:
    pivot = (high + low + close) / 3.0
    return {
        "p": pivot,
        "r1": 2 * pivot - low,
        "s1": 2 * pivot - high,
        "r2": pivot + (high - low),
        "s2": pivot - (high - low),
        "r3": high + 2 * (pivot - low),
        "s3": low - 2 * (high - pivot),
    }


def _aggregate(bars: list[dict]) -> dict:
    return {
        "o": bars[0]["o"],
        "h": max(float(b["h"]) for b in bars),
        "l": min(float(b["l"]) for b in bars),
        "c": bars[-1]["c"],
        "v": sum(float(b.get("v") or 0) for b in bars),
    }


def _completed_period_bars(candles: list[dict], kind: str) -> list[dict]:
    """Bars of the latest *completed* week/month (excludes current period)."""
    groups: list[tuple[tuple, list[dict]]] = []
    for bar in candles:
        try:
            dt = datetime.strptime(str(bar["t"]), "%Y-%m-%d")
        except (ValueError, TypeError):
            continue
        if kind == "week":
            iso = dt.isocalendar()
            key = (iso[0], iso[1])
        else:
            key = (dt.year, dt.month)
        if groups and groups[-1][0] == key:
            groups[-1][1].append(bar)
        else:
            groups.append((key, [bar]))
    if len(groups) >= 2:
        return groups[-2][1]
    return []


def pivot_analysis(candles: list[dict]) -> dict:
    result: dict = {"daily": None, "weekly": None, "monthly": None}
    if len(candles) >= 2:
        last = candles[-1]
        result["daily"] = {k: _r(v) for k, v in
                           classic_pivot(float(last["h"]), float(last["l"]), float(last["c"])).items()}
    for kind, key in (("week", "weekly"), ("month", "monthly")):
        bars = _completed_period_bars(candles, kind)
        if bars:
            agg = _aggregate(bars)
            result[key] = {k: _r(v) for k, v in
                           classic_pivot(float(agg["h"]), float(agg["l"]), float(agg["c"])).items()}
    return result


# --------------------------------------------------- support / resistance

def support_resistance(candles: list[dict], atr_value: float | None, lookback: int = 220, swing: int = 3) -> dict:
    """Cluster swing highs/lows into weighted support & resistance zones."""
    window = candles[-min(lookback, len(candles)):]
    n = len(window)
    last_close = float(window[-1]["c"])
    atr_v = atr_value or last_close * 0.02
    points: list[dict] = []
    for i in range(swing, n - swing):
        bar = window[i]
        high = float(bar["h"])
        low = float(bar["l"])
        if high >= max(float(window[j]["h"]) for j in range(i - swing, i + swing + 1)):
            points.append({"i": i, "price": high, "type": "H"})
        if low <= min(float(window[j]["l"]) for j in range(i - swing, i + swing + 1)):
            points.append({"i": i, "price": low, "type": "L"})
    if not points:
        return {"supports": [], "resistances": [], "tolerance": 0}
    points.sort(key=lambda p: p["price"])
    tolerance = max(last_close * 0.008, atr_v * 0.6)
    clusters: list[dict] = []
    for point in points:
        if clusters and abs(point["price"] - clusters[-1]["last_price"]) <= tolerance:
            cluster = clusters[-1]
            cluster["points"].append(point)
            cluster["last_price"] = point["price"]
        else:
            clusters.append({"points": [point], "last_price": point["price"]})
    levels = []
    for cluster in clusters:
        weights = []
        for p in cluster["points"]:
            recency = 1.0 + 1.5 * (p["i"] / max(1, n))
            weights.append((p, recency))
        total_weight = sum(w for _, w in weights)
        price = sum(p["price"] * w for p, w in weights) / total_weight
        last_point = max(weights, key=lambda x: x[0]["i"])[0]
        levels.append(
            {
                "price": _r(price),
                "touches": len(cluster["points"]),
                "score": _r(total_weight, 2),
                "last_date": _date_of(window[last_point["i"]]),
                "distance_pct": _r((price - last_close) / last_close * 100, 2),
            }
        )
    supports = [l for l in levels if l["price"] < last_close and l["distance_pct"] > -25]
    resistances = [l for l in levels if l["price"] > last_close and l["distance_pct"] < 25]
    supports.sort(key=lambda l: (-l["score"], abs(l["distance_pct"])))
    resistances.sort(key=lambda l: (-l["score"], abs(l["distance_pct"])))
    return {"supports": supports[:4], "resistances": resistances[:4], "tolerance": _r(tolerance)}


# ------------------------------------------------------------------ score

def _val(seq: list, idx: int):
    if 0 <= idx < len(seq):
        return seq[idx]
    return None


def compute_score(candles: list[dict], ind: dict, idx: int, *, piv_w=None, fib=None, sr=None,
                  include_levels: bool = True) -> dict:
    """Composite score in [-100, 100] from trend, momentum, levels, volume, pivots."""
    score = 0.0
    breakdown: list[dict] = []

    def add(points: float, group: str, text: str):
        nonlocal score
        if not points:
            return
        score += points
        breakdown.append({"group": group, "points": _r(points, 1), "text": text})

    closes = ind["closes"]
    close = closes[idx]
    prev_close = closes[idx - 1] if idx > 0 else close
    bar = candles[idx]

    # ----- trend (max ~ +/-30)
    ma20, ma50, ma200 = _val(ind["ma20"], idx), _val(ind["ma50"], idx), _val(ind["ma200"], idx)
    if ma20 is not None:
        add(6 if close > ma20 else -6, "trend", f"Giá {'trên' if close > ma20 else 'dưới'} SMA20")
    if ma50 is not None:
        add(8 if close > ma50 else -8, "trend", f"Giá {'trên' if close > ma50 else 'dưới'} SMA50")
    if ma200 is not None:
        add(8 if close > ma200 else -8, "trend", f"Giá {'trên' if close > ma200 else 'dưới'} SMA200")
    if ma20 is not None and ma50 is not None:
        add(5 if ma20 > ma50 else -5, "trend", f"SMA20 {'>' if ma20 > ma50 else '<'} SMA50")
    slope = ta.slope_pct(ind["ma50"], idx, 10)
    if slope is not None:
        add(3 if slope > 0 else -3, "trend", f"Độ dốc SMA50 {'tăng' if slope > 0 else 'giảm'} ({slope:.1f}%)")

    # ----- momentum (max ~ +/-26)
    rsi_now = _val(ind["rsi"], idx)
    rsi_prev = _val(ind["rsi"], idx - 3)
    if rsi_now is not None:
        if rsi_now >= 70:
            add(-10, "momentum", f"RSI {rsi_now:.0f} — quá mua")
        elif rsi_now >= 60:
            add(-2, "momentum", f"RSI {rsi_now:.0f} — vùng mạnh")
        elif rsi_now >= 45:
            add(0, "momentum", "")
        elif rsi_now >= 30:
            add(5, "momentum", f"RSI {rsi_now:.0f} — vùng tích lũy")
        else:
            add(10, "momentum", f"RSI {rsi_now:.0f} — quá bán")
        if rsi_prev is not None:
            add(3 if rsi_now > rsi_prev else -3, "momentum",
                f"RSI {'đang lên' if rsi_now > rsi_prev else 'đang xuống'} ({rsi_prev:.0f}→{rsi_now:.0f})")
    hist = _val(ind["macd_hist"], idx)
    hist_prev = _val(ind["macd_hist"], idx - 1)
    if hist is not None:
        add(6 if hist > 0 else -6, "momentum", f"MACD histogram {'dương' if hist > 0 else 'âm'}")
        if hist_prev is not None:
            add(3 if hist > hist_prev else -3, "momentum",
                f"MACD histogram {'mở rộng' if hist > hist_prev else 'thu hẹp'}")

    # ----- levels: fibonacci / S-R / breakout (only with context)
    if include_levels:
        if fib and fib.get("direction") == "UP":
            golden = fib.get("golden_zone") or []
            if len(golden) == 2 and golden[0] and golden[1] and golden[0] <= close <= golden[1]:
                add(12, "levels", "Giá trong vùng vàng Fibonacci 0.5–0.618")
            nearest_support = fib.get("nearest_support")
            if nearest_support and 0 < (close - nearest_support) / close <= 0.015:
                add(6, "levels", f"Giá sát hỗ trợ Fibonacci ({nearest_support:,.0f})")
            level_786 = (fib.get("level_map") or {}).get(0.786)
            if level_786 and close < level_786:
                add(-10, "levels", f"Giá phá vỡ Fib 0.786 ({level_786:,.0f}) — cấu trúc tăng bị tổn hại")
        if fib and fib.get("direction") == "DOWN":
            add(-8, "levels", "Cấu trúc Fibonacci đang trong xu hướng giảm")
        if sr:
            for resistance in (sr.get("resistances") or [])[:2]:
                if resistance["price"] and 0 < (resistance["price"] - close) / close <= 0.02:
                    add(-10, "levels", f"Gần kháng cự {resistance['price']:,.0f} ({resistance['touches']} lần chạm)")
                    break
            for support in (sr.get("supports") or [])[:1]:
                if support["price"] and support["touches"] >= 2 and close < support["price"]:
                    add(-6, "levels", f"Thủng hỗ trợ {support['price']:,.0f} ({support['touches']} lần chạm)")
        breakout_window = candles[max(0, idx - 60):idx]
        if breakout_window:
            recent_high = max(float(b["h"]) for b in breakout_window)
            vol_ma = _val(ind["vol_ma20"], idx)
            vol_ratio = (float(bar.get("v") or 0) / vol_ma) if vol_ma else None
            if close > recent_high and (vol_ratio or 0) >= 1.4:
                add(12, "levels", f"Bứt phá đỉnh 60 phiên kèm KL đột biến ({vol_ratio:.1f}×)")

    # ----- volume (max ~ +/-8)
    vol_ma = _val(ind["vol_ma20"], idx)
    if vol_ma:
        vol_ratio = float(bar.get("v") or 0) / vol_ma
        if close >= prev_close:
            if vol_ratio >= 1.5:
                add(6, "volume", f"KL tăng giá đột biến {vol_ratio:.1f}×")
            elif vol_ratio >= 1.0:
                add(3, "volume", f"KL tăng giá trên trung bình {vol_ratio:.1f}×")
        else:
            if vol_ratio >= 1.5:
                add(-6, "volume", f"KL bán tháo đột biến {vol_ratio:.1f}×")
            elif vol_ratio >= 1.0:
                add(-3, "volume", f"KL giảm giá trên trung bình {vol_ratio:.1f}×")

    # ----- pivots (max ~ +/-8)
    close_prev_bar = None
    if idx > 0:
        close_prev_bar = float(candles[idx - 1]["c"])
    if close_prev_bar:
        piv_d = classic_pivot(float(candles[idx - 1]["h"]), float(candles[idx - 1]["l"]), close_prev_bar)
        add(5 if close > piv_d["p"] else -5, "pivot", f"Giá {'trên' if close > piv_d['p'] else 'dưới'} Pivot ngày")
        if close > piv_d["r1"]:
            add(3, "pivot", "Giá vượt R1")
        elif close < piv_d["s1"]:
            add(-3, "pivot", "Giá dưới S1")
    if piv_w:
        wp = piv_w.get("p")
        if wp:
            add(2 if close > wp else -2, "pivot", f"Giá {'trên' if close > wp else 'dưới'} Pivot tuần")

    score = max(-100.0, min(100.0, score))
    breakdown.sort(key=lambda b: -abs(b["points"]))
    reasons = [b["text"] for b in breakdown if b["text"]]
    return {"score": _r(score, 1), "breakdown": breakdown, "reasons": reasons}


def signal_from_score(score: float) -> dict:
    if score >= SIGNAL_STRONG_BUY:
        code = "STRONG_BUY"
    elif score >= SIGNAL_BUY:
        code = "BUY"
    elif score <= SIGNAL_STRONG_SELL:
        code = "STRONG_SELL"
    elif score <= SIGNAL_SELL:
        code = "SELL"
    else:
        code = "HOLD"
    meta = SIGNAL_META[code]
    return {"code": code, "label": meta["label"], "tone": meta["tone"], "score": _r(score, 1)}


# ---------------------------------------------------------------- backtest

def backtest_signals(candles: list[dict], ind: dict, buy_th: float = SIGNAL_BUY,
                     sell_th: float = SIGNAL_SELL, max_bars: int = 300) -> dict:
    """Bar-by-bar signal simulation used for win-rate / payoff (Kelly inputs)."""
    n = len(candles)
    empty = {"trades": [], "markers": [], "stats": None, "score_history": []}
    if n < 90:
        return empty
    start = max(62, n - max_bars)
    score_history: list[dict] = []
    for i in range(start - 1, n):
        res = compute_score(candles, ind, i, include_levels=False)
        score_history.append({"i": i, "t": _date_of(candles[i]), "score": res["score"]})
    scores = {item["i"]: item["score"] for item in score_history}

    trades: list[dict] = []
    markers: list[dict] = []
    position = None
    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    for i in range(start, n):
        current_score = scores.get(i)
        if current_score is None:
            continue
        if position is None:
            prev_score = scores.get(i - 1, current_score)
            if current_score >= buy_th and prev_score < buy_th and i + 1 < n:
                entry = float(candles[i + 1]["o"])
                atr_i = _val(ind["atr"], i) or entry * 0.03
                stop = entry - 1.5 * atr_i
                risk = entry - stop
                if risk > 0:
                    position = {
                        "entry": entry,
                        "stop": stop,
                        "target": entry + 2.0 * risk,
                        "entry_idx": i + 1,
                        "entry_t": _date_of(candles[i + 1]),
                    }
                    markers.append({"t": position["entry_t"], "type": "buy", "price": _r(entry), "text": "MUA"})
        else:
            bar = candles[i]
            exit_price = None
            kind = None
            if float(bar["l"]) <= position["stop"]:
                exit_price, kind = position["stop"], "stop"
            elif float(bar["h"]) >= position["target"]:
                exit_price, kind = position["target"], "target"
            elif current_score <= sell_th:
                exit_price = float(candles[i + 1]["o"]) if i + 1 < n else float(bar["c"])
                kind = "signal"
            elif i - position["entry_idx"] >= 60:
                exit_price, kind = float(bar["c"]), "time"
            if exit_price is not None:
                ret = (exit_price - position["entry"]) / position["entry"]
                trades.append(
                    {
                        "entry_t": position["entry_t"],
                        "exit_t": _date_of(bar),
                        "entry": _r(position["entry"]),
                        "exit": _r(exit_price),
                        "ret_pct": _r(ret * 100, 2),
                        "kind": kind,
                    }
                )
                markers.append({"t": _date_of(bar), "type": "sell", "price": _r(exit_price), "text": "BÁN"})
                equity *= 1.0 + ret
                peak = max(peak, equity)
                max_dd = min(max_dd, (equity - peak) / peak)
                position = None

    stats = None
    if trades:
        wins = [t["ret_pct"] for t in trades if t["ret_pct"] > 0]
        losses = [t["ret_pct"] for t in trades if t["ret_pct"] <= 0]
        win_rate = len(wins) / len(trades)
        avg_win = sum(wins) / len(wins) if wins else 0.0
        avg_loss = sum(losses) / len(losses) if losses else 0.0
        payoff = (avg_win / abs(avg_loss)) if (wins and losses and avg_loss != 0) else None
        expectancy = win_rate * avg_win + (1 - win_rate) * avg_loss
        stats = {
            "trades": len(trades),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": _r(win_rate * 100, 1),
            "avg_win_pct": _r(avg_win, 2),
            "avg_loss_pct": _r(avg_loss, 2),
            "payoff": _r(payoff, 2),
            "expectancy_pct": _r(expectancy, 2),
            "max_drawdown_pct": _r(max_dd * 100, 1),
            "profit_factor": _r((len(wins) * avg_win) / abs(len(losses) * avg_loss), 2)
            if (losses and avg_loss != 0) else None,
        }
    return {
        "trades": trades[-12:],
        "markers": markers[-14:],
        "stats": stats,
        "score_history": score_history,
    }


# ------------------------------------------------------------ action levels

def _dedupe_levels(candidates: list[dict], reference: float, tolerance_pct: float = 0.8) -> list[dict]:
    kept: list[dict] = []
    for candidate in candidates:
        if candidate["price"] is None:
            continue
        if any(abs(candidate["price"] - k["price"]) / reference * 100 <= tolerance_pct for k in kept):
            continue
        kept.append(candidate)
    return kept


def action_levels(price: float, atr_value: float | None, fib: dict, sr: dict, pivots: dict,
                  signal_code: str) -> dict:
    """Actionable 'diem mua / diem ban' levels with stop loss and risk/reward."""
    atr = atr_value or price * 0.02
    level_map = (fib or {}).get("level_map") or {}
    ext_map = (fib or {}).get("ext_map") or {}

    # ---- buy points (ho tro)
    buy_candidates: list[dict] = []
    if fib and fib.get("direction") == "UP":
        for ratio, label in ((0.5, "Mua 1 · Fib 0.50"), (0.618, "Mua 2 · Fib 0.618"), (0.786, "Mua 3 · Fib 0.786 (dự phòng)")):
            level = level_map.get(ratio)
            if level:
                buy_candidates.append({"price": level, "label": label, "kind": "fib"})
    if fib and fib.get("direction") == "DOWN":
        anchor_low = (fib.get("anchor_low") or {}).get("price")
        if anchor_low:
            buy_candidates.append({"price": anchor_low, "label": "Mua thăm dò · Đáy gần nhất", "kind": "fib"})
    for support in (sr.get("supports") or []):
        if support.get("touches", 0) >= 2:
            buy_candidates.append(
                {"price": support["price"], "label": f"Mua · Hỗ trợ {support['touches']} lần chạm", "kind": "support"}
            )
    daily = (pivots or {}).get("daily") or {}
    for key, label in (("s1", "Mua · Pivot S1"), ("s2", "Mua · Pivot S2")):
        if daily.get(key):
            buy_candidates.append({"price": daily[key], "label": label, "kind": "pivot"})
    buy_candidates = [c for c in buy_candidates if c["price"] <= price * 1.015 and c["price"] > 0]
    buy_candidates.sort(key=lambda c: -c["price"])
    buy_points = _dedupe_levels(buy_candidates, price)[:3]

    # ---- sell points / targets (khang cu)
    sell_candidates: list[dict] = []
    if fib:
        for ratio, label in ((1.272, "Chốt lời 1 · Fib mở rộng 1.272"), (1.618, "Chốt lời 2 · Fib mở rộng 1.618")):
            level = ext_map.get(ratio)
            if level:
                sell_candidates.append({"price": level, "label": label, "kind": "fib"})
        anchor_high = (fib.get("anchor_high") or {}).get("price")
        if anchor_high and anchor_high > price * 1.005:
            sell_candidates.append({"price": anchor_high, "label": "Chốt lời · Đỉnh swing gần nhất", "kind": "fib"})
    for resistance in (sr.get("resistances") or []):
        if resistance.get("touches", 0) >= 2:
            sell_candidates.append(
                {"price": resistance["price"], "label": f"Bán · Kháng cự {resistance['touches']} lần chạm", "kind": "resistance"}
            )
    for key, label in (("r1", "Bán · Pivot R1"), ("r2", "Bán · Pivot R2")):
        if daily.get(key):
            sell_candidates.append({"price": daily[key], "label": label, "kind": "pivot"})
    sell_candidates = [c for c in sell_candidates if c["price"] >= price * 1.005]
    sell_candidates.sort(key=lambda c: c["price"])
    sell_points = _dedupe_levels(sell_candidates, price)[:3]

    # ---- stop loss (duoi ho tro gan nhat)
    stop_candidates: list[float] = [price - 2.0 * atr]
    level_786 = level_map.get(0.786)
    if fib and fib.get("direction") == "UP" and level_786:
        stop_candidates.append(level_786 - 0.5 * atr)
    strong_supports = [s["price"] for s in (sr.get("supports") or []) if s.get("touches", 0) >= 2]
    if strong_supports:
        stop_candidates.append(max(strong_supports) - 0.5 * atr)
    valid_stops = [s for s in stop_candidates if s and s <= price - atr * 0.8]
    stop_loss = max(valid_stops) if valid_stops else price - 1.5 * atr
    stop_loss = min(stop_loss, price * 0.985)  # toi thieu -1.5%

    golden = (fib or {}).get("golden_zone") or []
    buy_zone = [b for b in golden if b] if (len(golden) == 2 and (fib or {}).get("direction") == "UP") else []
    risk_reward = None
    if sell_points and stop_loss < price:
        risk_reward = _r((sell_points[0]["price"] - price) / (price - stop_loss), 2)

    warnings: list[str] = []
    if signal_code in {"SELL", "STRONG_SELL"}:
        warnings.append("Tín hiệu bán — ưu tiên bảo toàn vốn, chờ xác nhận tạo đáy trước khi mua.")
    if fib and fib.get("direction") == "DOWN":
        warnings.append("Fibonacci đang trong cấu trúc giảm — điểm mua chỉ mang tính bắt đáy thăm dò.")
    if stop_loss and (price - stop_loss) / price > 0.08:
        warnings.append("Khoảng cách cắt lỗ khá xa (>8%) — giảm khối lượng cho phù hợp khẩu vị rủi ro.")

    return {
        "entry": _r(price),
        "buy_points": [{"label": c["label"], "price": _r(c["price"]), "kind": c["kind"]} for c in buy_points],
        "sell_points": [{"label": c["label"], "price": _r(c["price"]), "kind": c["kind"]} for c in sell_points],
        "stop_loss": _r(stop_loss),
        "buy_zone": [_r(buy_zone[0]), _r(buy_zone[1])] if buy_zone else [],
        "risk_reward": risk_reward,
        "warnings": warnings,
    }


# -------------------------------------------------------------- entrypoint

def analyze_symbol(symbol: str, candles: list[dict], settings: dict | None = None,
                   fundamentals: dict | None = None, meta: dict | None = None) -> dict:
    """Full analysis payload for one symbol (consumed by the UI and stores)."""
    settings = settings or {}
    days = int(settings.get("history_days") or 400)
    candles = sorted(candles, key=lambda c: str(c["t"]))[-days:]
    if len(candles) < 60:
        raise ValueError(f"Không đủ dữ liệu lịch sử cho {symbol} (cần tối thiểu 60 phiên)")

    ind = compute_indicator_bundle(candles)
    closes = ind["closes"]
    price = closes[-1]
    prev_close = closes[-2] if len(closes) > 1 else price
    atr_last = ta.last(ind["atr"])
    fib = fib_analysis(candles)
    pivots = pivot_analysis(candles)
    sr = support_resistance(candles, atr_last)

    scored = compute_score(candles, ind, len(candles) - 1, piv_w=pivots.get("weekly"), fib=fib, sr=sr)
    signal = signal_from_score(scored["score"])
    levels = action_levels(price, atr_last, fib, sr, pivots, signal["code"])
    backtest = backtest_signals(candles, ind)

    vol_ma = ta.last(ind["vol_ma20"])
    last_vol = float(candles[-1].get("v") or 0)
    fundamentals_payload = None
    if fundamentals:
        div_ps = fundamentals.get("div_ps_ttm")
        fundamentals_payload = {
            "dividend_ttm": _r(div_ps, 0) if div_ps else None,
            "dividend_yield": _r(div_ps / price * 100, 2) if div_ps and price else None,
            "market_cap": fundamentals.get("market_cap"),
            "rating": fundamentals.get("rating"),
            "target_price": fundamentals.get("target_price"),
            "sector": fundamentals.get("sector"),
            "dividend_events": fundamentals.get("dividend_events") or [],
        }

    payload = {
        "symbol": symbol.upper(),
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "meta": meta or {},
        "price": _r(price),
        "prev_close": _r(prev_close),
        "change_pct": _r((price - prev_close) / prev_close * 100, 2) if prev_close else None,
        "candles": candles,
        "sma": {"ma20": ind["ma20"], "ma50": ind["ma50"], "ma200": ind["ma200"]},
        "rsi_series": ind["rsi"],
        "macd_hist": ind["macd_hist"],
        "indicators": {
            "rsi": _r(ta.last(ind["rsi"]), 1),
            "macd_hist": _r(ta.last(ind["macd_hist"]), 2),
            "macd_line": _r(ta.last(ind["macd_line"]), 2),
            "macd_signal": _r(ta.last(ind["macd_signal"]), 2),
            "atr": _r(atr_last),
            "volume_ratio": _r(last_vol / vol_ma, 2) if vol_ma else None,
            "bb_upper": _r(ta.last(ind["bb_upper"])),
            "bb_lower": _r(ta.last(ind["bb_lower"])),
            "ma20": _r(ta.last(ind["ma20"])),
            "ma50": _r(ta.last(ind["ma50"])),
            "ma200": _r(ta.last(ind["ma200"])),
        },
        "fib": {k: v for k, v in fib.items() if k not in {"level_map", "ext_map"}},
        "pivots": pivots,
        "supports": sr.get("supports"),
        "resistances": sr.get("resistances"),
        "signal": signal,
        "score_breakdown": scored["breakdown"],
        "reasons": scored["reasons"][:8],
        "levels": levels,
        "backtest": backtest["stats"],
        "markers": backtest["markers"],
        "score_history": backtest["score_history"],
        "fundamentals": fundamentals_payload,
        "thresholds": {
            "strong_buy": SIGNAL_STRONG_BUY,
            "buy": SIGNAL_BUY,
            "sell": SIGNAL_SELL,
            "strong_sell": SIGNAL_STRONG_SELL,
        },
    }
    return payload
