"""Advanced analysis: trend momentum, swing peaks/troughs and reversal patterns.

Contains the user-supplied reference implementation (evaluate_trend_signal,
analyze_chart_patterns with cup & handle / double bottom / double top /
head & shoulders / inverse H&S / morning star) extended with classic
Japanese candlestick reversal patterns (evening star, hammer, shooting star,
bullish/bearish engulfing, doji) and a swing-structure summary.
"""
from __future__ import annotations

import statistics
from datetime import datetime

from . import db

_PIVOT_WINDOW = 2


def _valid_prices(values):
    prices = []
    for value in values or []:
        try:
            price = float(value)
        except (TypeError, ValueError):
            continue
        if price > 0:
            prices.append(price)
    return prices


def _valid_volumes(values):
    volumes = []
    for value in values or []:
        try:
            volume = float(value)
        except (TypeError, ValueError):
            continue
        if volume >= 0:
            volumes.append(volume)
    return volumes


def _pivots(values, kind):
    pivots = []
    for index in range(_PIVOT_WINDOW, len(values) - _PIVOT_WINDOW):
        value = values[index]
        before = values[index - _PIVOT_WINDOW:index]
        after = values[index + 1:index + _PIVOT_WINDOW + 1]
        if kind == "high" and value >= max(before) and value > max(after):
            pivots.append((index, value))
        elif kind == "low" and value <= min(before) and value < min(after):
            pivots.append((index, value))
    return pivots


def _volume_ratio(volumes):
    if len(volumes) < 21:
        return None
    baseline = statistics.mean(volumes[-21:-1])
    if baseline <= 0:
        return None
    return volumes[-1] / baseline


def _result(
    name,
    signal,
    message,
    neckline=None,
    support=None,
    volume_ratio=None,
    volume_basis="TB20",
):
    return {
        "name": name,
        "signal": signal,
        "message": message,
        "neckline": round(neckline, 2) if neckline is not None else None,
        "support": round(support, 2) if support is not None else None,
        "volume_ratio": round(volume_ratio, 2) if volume_ratio is not None else None,
        "volume_basis": volume_basis,
    }


def evaluate_trend_signal(prices):
    if not prices:
        return {"signal": "Neutral", "momentum": 0.0, "score": 0.0}

    first_price = prices[0]
    last_price = prices[-1]
    momentum = ((last_price - first_price) / first_price) * 100

    if momentum >= 5:
        signal = "Bullish"
    elif momentum <= -3:
        signal = "Bearish"
    else:
        signal = "Neutral"

    return {
        "signal": signal,
        "momentum": round(momentum, 2),
        "score": round(momentum * 1.4, 2),
        "last_price": round(last_price, 2),
    }


def _cup_and_handle(prices, volume_ratio):
    name = "Cốc tay cầm"
    if len(prices) < 60:
        return _result(name, "Không đủ dữ liệu", "Cần ít nhất 60 phiên giá.", volume_ratio=volume_ratio)

    window = prices[-60:]
    left_rim = max(window[:15])
    cup_bottom = min(window[15:40])
    right_rim = max(window[40:50])
    handle_low = min(window[50:59])
    depth = (left_rim - cup_bottom) / left_rim if left_rim else 0
    rim_difference = abs(right_rim - left_rim) / left_rim if left_rim else 1
    handle_retracement = (
        (right_rim - handle_low) / (left_rim - cup_bottom)
        if left_rim > cup_bottom
        else 1
    )

    structure_valid = (
        0.12 <= depth <= 0.35
        and rim_difference <= 0.05
        and 0.10 <= handle_retracement <= 0.50
        and handle_low > cup_bottom
    )
    if not structure_valid:
        return _result(name, "Không có mẫu", "Chưa thấy cấu trúc cốc và tay cầm rõ.", volume_ratio=volume_ratio)

    current_price = prices[-1]
    volume_confirmed = volume_ratio is not None and volume_ratio >= 1.5
    if current_price < handle_low and volume_confirmed:
        return _result(
            name,
            "Bán",
            "Giá thủng hỗ trợ tay cầm kèm volume cao.",
            neckline=left_rim,
            support=handle_low,
            volume_ratio=volume_ratio,
        )
    if current_price > max(left_rim, right_rim) and volume_confirmed:
        return _result(
            name,
            "Mua",
            "Breakout khỏi miệng cốc, volume đạt ít nhất 1.5× trung bình 20 phiên.",
            neckline=max(left_rim, right_rim),
            support=handle_low,
            volume_ratio=volume_ratio,
        )
    return _result(
        name,
        "Theo dõi",
        "Mẫu hình đã hình thành; chờ breakout có volume xác nhận hoặc thủng hỗ trợ tay cầm.",
        neckline=max(left_rim, right_rim),
        support=handle_low,
        volume_ratio=volume_ratio,
    )


def _double_bottom(prices):
    name = "Hai đáy"
    lows = _pivots(prices[-100:], "low")
    for second_index in range(len(lows) - 1, 0, -1):
        second_at, second_price = lows[second_index]
        for first_at, first_price in reversed(lows[:second_index]):
            separation = second_at - first_at
            similar = abs(second_price - first_price) / ((second_price + first_price) / 2)
            if not 7 <= separation <= 50 or similar > 0.03:
                continue
            neckline = max(prices[-100:][first_at + 1:second_at])
            if neckline < max(first_price, second_price) * 1.04:
                continue
            current_price = prices[-1]
            if current_price > neckline:
                return _result(name, "Mua", "Giá đã vượt neckline xác nhận mô hình hai đáy.", neckline, min(first_price, second_price))
            return _result(name, "Theo dõi", "Hai đáy tiềm năng; chờ giá đóng cửa vượt neckline.", neckline, min(first_price, second_price))
    return _result(name, "Không có mẫu", "Chưa thấy hai đáy cân xứng rõ.")


def _double_top(prices):
    name = "Hai đỉnh"
    highs = _pivots(prices[-100:], "high")
    for second_index in range(len(highs) - 1, 0, -1):
        second_at, second_price = highs[second_index]
        for first_at, first_price in reversed(highs[:second_index]):
            separation = second_at - first_at
            similar = abs(second_price - first_price) / ((second_price + first_price) / 2)
            if not 7 <= separation <= 50 or similar > 0.03:
                continue
            neckline = min(prices[-100:][first_at + 1:second_at])
            if neckline > min(first_price, second_price) * 0.96:
                continue
            current_price = prices[-1]
            if current_price < neckline:
                return _result(name, "Bán", "Giá đã thủng neckline xác nhận mô hình hai đỉnh.", neckline, max(first_price, second_price))
            return _result(name, "Theo dõi", "Hai đỉnh tiềm năng; chờ giá đóng cửa thủng neckline.", neckline, max(first_price, second_price))
    return _result(name, "Không có mẫu", "Chưa thấy hai đỉnh cân xứng rõ.")


def _head_and_shoulders(prices):
    name = "Vai đầu vai"
    window = prices[-100:]
    highs = _pivots(window, "high")
    for index in range(len(highs) - 1, 1, -1):
        left = highs[index - 2]
        head = highs[index - 1]
        right = highs[index]
        left_at, left_price = left
        head_at, head_price = head
        right_at, right_price = right
        shoulders_match = abs(left_price - right_price) / ((left_price + right_price) / 2) <= 0.05
        head_prominence = head_price >= max(left_price, right_price) * 1.05
        spaced = head_at - left_at >= 4 and right_at - head_at >= 4
        if not shoulders_match or not head_prominence or not spaced:
            continue

        left_trough = min(window[left_at + 1:head_at])
        right_trough = min(window[head_at + 1:right_at])
        neckline = (left_trough + right_trough) / 2
        if prices[-1] < neckline:
            return _result(name, "Bán", "Giá đóng cửa đã phá neckline mô hình vai đầu vai.", neckline, min(left_price, right_price))
        return _result(name, "Theo dõi", "Vai đầu vai tiềm năng; chờ giá đóng cửa phá neckline.", neckline, min(left_price, right_price))
    return _result(name, "Không có mẫu", "Chưa thấy cấu trúc vai đầu vai rõ.")


def _average_pivot_volume(volumes, index):
    sample = [volume for volume in volumes[max(0, index - 2):index + 3] if volume is not None]
    return statistics.mean(sample) if len(sample) == 5 else None


def _inverse_head_and_shoulders(prices, volumes):
    name = "Vai đầu vai ngược"
    window = prices[-100:]
    offset = len(prices) - len(window)
    lows = _pivots(window, "low")
    for index in range(len(lows) - 1, 1, -1):
        left = lows[index - 2]
        head = lows[index - 1]
        right = lows[index]
        left_at, left_price = left
        head_at, head_price = head
        right_at, right_price = right
        shoulders_match = abs(left_price - right_price) / ((left_price + right_price) / 2) <= 0.05
        head_prominence = head_price <= min(left_price, right_price) * 0.95
        spaced = head_at - left_at >= 4 and right_at - head_at >= 4
        if not shoulders_match or not head_prominence or not spaced:
            continue

        left_peak = max(window[left_at + 1:head_at])
        right_peak = max(window[head_at + 1:right_at])
        neckline = (left_peak + right_peak) / 2
        left_volume = _average_pivot_volume(volumes, offset + left_at)
        head_volume = _average_pivot_volume(volumes, offset + head_at)
        right_volume = _average_pivot_volume(volumes, offset + right_at)
        volume_contraction = (
            left_volume is not None
            and head_volume is not None
            and right_volume is not None
            and right_volume < left_volume
            and right_volume < head_volume
        )
        volume_ratio = (
            right_volume / max(left_volume, head_volume)
            if volume_contraction
            else None
        )
        breakout = prices[-1] > neckline
        if breakout and volume_contraction:
            return _result(
                name,
                "Mua",
                "Giá vượt neckline; volume vai phải thấp hơn vai trái và đầu.",
                neckline,
                head_price,
                volume_ratio,
                "vai phải/vai trái-đầu",
            )
        message = (
            "Đã vượt neckline nhưng volume vai phải chưa xác nhận giảm."
            if breakout
            else "Mẫu hình tiềm năng; chờ vượt neckline và volume vai phải thấp hơn vai trái/đầu."
        )
        return _result(
            name,
            "Theo dõi",
            message,
            neckline,
            head_price,
            volume_ratio,
            "vai phải/vai trái-đầu",
        )
    return _result(name, "Không có mẫu", "Chưa thấy cấu trúc vai đầu vai ngược rõ.")


# ------------------------------------------------------- candle primitives

def _ohlc(candles):
    """Normalize candle dicts (t/o/h/l/c or open/high/low/close) for patterns."""
    out = []
    for candle in candles or []:
        try:
            out.append(
                {
                    "date": candle.get("t") or candle.get("date"),
                    "open": float(candle.get("o", candle.get("open"))),
                    "high": float(candle.get("h", candle.get("high"))),
                    "low": float(candle.get("l", candle.get("low"))),
                    "close": float(candle.get("c", candle.get("close"))),
                }
            )
        except (TypeError, ValueError):
            continue
    return out


def _star(candles, bullish: bool):
    """Three-candle reversal star (Sao Mai bullish / Sao Hoài bearish)."""
    name = "Sao Mai" if bullish else "Sao Hoài"
    if len(candles) < 3:
        return _result(name, "Không đủ dữ liệu", "Cần OHLC của ít nhất 3 phiên.")

    first, middle, third = candles[-3:]
    first_range = first["high"] - first["low"]
    middle_range = middle["high"] - middle["low"]
    third_range = third["high"] - third["low"]
    if min(first_range, middle_range, third_range) <= 0:
        return _result(name, "Không có mẫu", "Biên độ nến không hợp lệ.")

    if bullish:
        first_body = first["open"] - first["close"]
        middle_body = abs(middle["close"] - middle["open"])
        third_body = third["close"] - third["open"]
        first_midpoint = (first["open"] + first["close"]) / 2
        structure_valid = (
            first_body / first_range >= 0.55
            and middle_body / middle_range <= 0.30
            and third_body / third_range >= 0.55
            and third["close"] > first_midpoint
            and third["close"] > middle["high"]
        )
    else:
        first_body = first["close"] - first["open"]
        middle_body = abs(middle["close"] - middle["open"])
        third_body = third["open"] - third["close"]
        first_midpoint = (first["open"] + first["close"]) / 2
        structure_valid = (
            first_body / first_range >= 0.55
            and middle_body / middle_range <= 0.30
            and third_body / third_range >= 0.55
            and third["close"] < first_midpoint
            and third["close"] < middle["low"]
        )
    if not structure_valid:
        return _result(name, "Không có mẫu", f"Ba nến cuối chưa tạo cấu trúc {name} rõ.")

    if bullish:
        return _result(
            name,
            "Theo dõi",
            "Có cấu trúc Sao Mai (đảo chiều tăng); chờ volume nến thứ ba xác nhận (≥1.5× TB20).",
            first_midpoint,
            first["low"],
        )
    return _result(
        name,
        "Bán",
        "Sao Hoài — ba nến đảo chiều giảm sau xu hướng tăng; ưu tiên chốt lời hoặc cắt lỗ.",
        first_midpoint,
        third["close"],
    )


def _hammer_like(candles, bullish: bool):
    """Búa (bullish) / Sao băng (bearish): long shadow against the trend."""
    name = "Búa" if bullish else "Sao băng"
    if len(candles) < 5:
        return _result(name, "Không đủ dữ liệu", "Cần OHLC của ít nhất 5 phiên.")
    candle = candles[-1]
    body = abs(candle["close"] - candle["open"])
    candle_range = candle["high"] - candle["low"]
    if candle_range <= 0:
        return _result(name, "Không có mẫu", "Biên độ nến không hợp lệ.")
    upper_shadow = candle["high"] - max(candle["open"], candle["close"])
    lower_shadow = min(candle["open"], candle["close"]) - candle["low"]

    if bullish:
        shadow_ok = lower_shadow >= 2 * body and upper_shadow <= body
        closes_before = [c["close"] for c in candles[-5:-1]]
        downtrend = closes_before[0] > closes_before[-1]
    else:
        shadow_ok = upper_shadow >= 2 * body and lower_shadow <= body
        closes_before = [c["close"] for c in candles[-5:-1]]
        downtrend = closes_before[0] < closes_before[-1]
    if not shadow_ok:
        return _result(name, "Không có mẫu", "Nến cuối không có bóng đặc trưng của mẫu hình.")
    if not downtrend:
        direction = "giảm" if bullish else "tăng"
        return _result(name, "Theo dõi", f"Có hình thái {name} nhưng chưa có xu hướng {direction} rõ phía trước.")

    if bullish:
        return _result(
            name,
            "Theo dõi",
            "Nến Búa cuối đáy giảm — dấu hiệu mua về; chờ nến xác nhận tăng phiên kế tiếp.",
            None,
            candle["low"],
        )
    return _result(
        name,
        "Bán",
        "Sao băng cuối đỉnh tăng — áp lực bán mạnh ở vùng cao; ưu tiên chốt lời/cắt lỗ.",
        None,
        candle["high"],
    )


def _engulfing(candles, bullish: bool):
    name = "Bao phủ tăng" if bullish else "Bao phủ giảm"
    if len(candles) < 3:
        return _result(name, "Không đủ dữ liệu", "Cần OHLC của ít nhất 3 phiên.")
    prev, curr = candles[-2], candles[-1]
    prev_bull = prev["close"] >= prev["open"]
    curr_bull = curr["close"] >= curr["open"]
    if bullish and (prev_bull or not curr_bull):
        return _result(name, "Không có mẫu", "Hai nến cuối không phải nến đỏ rồi nến xanh bao phủ.")
    if not bullish and (not prev_bull or curr_bull):
        return _result(name, "Không có mẫu", "Hai nến cuối không phải nến xanh rồi nến đỏ bao phủ.")

    prev_top = max(prev["open"], prev["close"])
    prev_bottom = min(prev["open"], prev["close"])
    curr_top = max(curr["open"], curr["close"])
    curr_bottom = min(curr["open"], curr["close"])
    engulfs = curr_top >= prev_top and curr_bottom <= prev_bottom
    if not engulfs:
        return _result(name, "Không có mẫu", "Thân nến sau chưa bao phủ trọn thân nến trước.")

    if bullish:
        return _result(
            name,
            "Theo dõi",
            "Nến xanh bao phủ nến đỏ — tín hiệu đảo chiều tăng tiềm năng; chờ xác nhận bằng nến tăng kế tiếp.",
            None,
            curr["low"],
        )
    return _result(
        name,
        "Bán",
        "Nến đỏ bao phủ nến xanh — tín hiệu đảo chiều giảm tiềm năng; cảnh giác phân phối ở vùng cao.",
        None,
        curr["high"],
    )


def _doji(candles):
    name = "Doji"
    if len(candles) < 2:
        return _result(name, "Không đủ dữ liệu", "Cần OHLC của ít nhất 2 phiên.")
    candle = candles[-1]
    candle_range = candle["high"] - candle["low"]
    body = abs(candle["close"] - candle["open"])
    if candle_range <= 0 or body / candle_range > 0.1:
        return _result(name, "Không có mẫu", "Nến cuối không phải Doji (thân nến quá lớn).")
    return _result(
        name,
        "Theo dõi",
        "Doji — thế cân bằng, thị trường phân vân; chờ nến xác nhận hướng đi tiếp theo.",
        None,
        (candle["high"] + candle["low"]) / 2,
    )


def analyze_chart_patterns(prices, volumes=None, candles=None):
    """Price-structure patterns (user reference implementation)."""
    valid_prices = _valid_prices(prices)
    valid_volumes = _valid_volumes(volumes)
    aligned_volumes = []
    for volume in volumes or []:
        try:
            value = float(volume)
        except (TypeError, ValueError):
            value = None
        aligned_volumes.append(value if value is not None and value >= 0 else None)
    volume_ratio = _volume_ratio(valid_volumes)
    if len(valid_volumes) != len(valid_prices):
        volume_ratio = None

    ohlc = _ohlc(candles) if candles else []
    return [
        _cup_and_handle(valid_prices, volume_ratio),
        _double_bottom(valid_prices),
        _double_top(valid_prices),
        _head_and_shoulders(valid_prices),
        _star(ohlc, bullish=True),
        _inverse_head_and_shoulders(valid_prices, aligned_volumes),
    ]


def analyze_candle_reversals(candles):
    """Japanese candlestick reversal patterns on the most recent sessions."""
    ohlc = _ohlc(candles)
    return [
        _star(ohlc, bullish=False),
        _hammer_like(ohlc, bullish=True),
        _hammer_like(ohlc, bullish=False),
        _engulfing(ohlc, bullish=True),
        _engulfing(ohlc, bullish=False),
        _doji(ohlc),
    ]


def swing_points(candles, limit: int = 3) -> dict:
    """Recent swing peaks (đỉnh) and troughs (đáy) with dates + structure note."""
    closes = [float(c["c"]) for c in candles if c.get("c")]
    window = candles[-100:]
    highs = _pivots([float(c["h"]) for c in window], "high")
    lows = _pivots([float(c["l"]) for c in window], "low")

    def fmt(points):
        out = []
        for index, value in points[-limit:]:
            date = window[index].get("t") if 0 <= index < len(window) else None
            out.append({"date": date, "price": round(value, 2)})
        return out

    peaks, troughs = fmt(highs), fmt(lows)
    structure = "Cấu trúc trung tính"
    if len(peaks) >= 2 and len(troughs) >= 2:
        higher_high = peaks[-1]["price"] > peaks[-2]["price"]
        higher_low = troughs[-1]["price"] > troughs[-2]["price"]
        if higher_high and higher_low:
            structure = "Đỉnh và đáy nâng dần — xu hướng TĂNG"
        elif not higher_high and not higher_low:
            structure = "Đỉnh và đáy hạ dần — xu hướng GIẢM"
        elif not higher_high and higher_low:
            structure = "Đỉnh hạ, đáy nâng — tam giác hội tụ, chờ phá vỡ"
        else:
            structure = "Đỉnh nâng, đáy hạ — nở rộng bất định, thận trọng"
    return {
        "peaks": peaks,
        "troughs": troughs,
        "structure": structure,
        "window_sessions": len(window),
    }


def analyze_advanced(symbol: str, candles: list[dict]) -> dict:
    """Full advanced module: trend momentum + swings + both pattern groups."""
    candles = sorted(candles, key=lambda c: str(c["t"]))
    closes = [float(c["c"]) for c in candles]
    volumes = [c.get("v") for c in candles]
    trend = evaluate_trend_signal(closes)
    chart = analyze_chart_patterns(closes, volumes, candles)
    candle_hits = analyze_candle_reversals(candles)
    swing = swing_points(candles)

    score = 0
    if trend["signal"] == "Bullish":
        score += 2
    elif trend["signal"] == "Bearish":
        score -= 2
    for row in chart + candle_hits:
        if row["signal"] == "Mua":
            score += 1
        elif row["signal"] == "Bán":
            score -= 1
    if score >= 2:
        bias, bias_label = "Bullish", "Nghiêng TĂNG"
    elif score <= -2:
        bias, bias_label = "Bearish", "Nghiêng GIẢM"
    else:
        bias, bias_label = "Neutral", "TRUNG TÍNH"

    active = [r["name"] for r in chart + candle_hits if r["signal"] in {"Mua", "Bán"}]
    summary = (
        f"{bias_label}: động lượng {trend['signal']} ({trend['momentum']:+.2f}% cửa sổ phân tích), "
        f"{swing['structure'].lower()}."
        + (f" Mẫu hình đang kích hoạt: {', '.join(active)}." if active else " Chưa có mẫu hình nào kích hoạt tín hiệu.")
    )
    return {
        "symbol": symbol.upper(),
        "updated_at": db.now_str(),
        "last_price": round(closes[-1], 2) if closes else None,
        "sessions": len(candles),
        "trend": trend,
        "swing": swing,
        "chart_patterns": chart,
        "candle_patterns": candle_hits,
        "bias": bias,
        "bias_label": bias_label,
        "summary": summary,
    }
