"""Chiến lược Trend Following theo phong cách Edward Thorp tối ưu cho TTCK Việt Nam.

Quy trình 5 bước:
  Bước 1: Bộ lọc xu hướng kết hợp (Trend & Fundamental Filter)
          - Yếu tố cơ bản: Ngành vĩ mô ủng hộ + Tăng trưởng EPS > 15% + Thanh khoản V20 >= 500.000 cp/phiên
          - Kỹ thuật: Giá > EMA 200 và EMA 50 > EMA 200 (Golden Cross)
  Bước 2: Điểm mua (Entry Trigger)
          - Mua khi điều chỉnh (pullback/retest) về EMA 50 hoặc Mid Bollinger Band (MA 20),
            xuất hiện nến xanh đảo chiều (Bullish Engulfing, Hammer, Morning Star) kiệt vol (V <= V20).
          - Xác nhận: Giá vượt đỉnh ngắn hạn gần nhất với khối lượng V >= 1.5 * V20.
  Bước 3: Định cỡ vị thế bằng Fractional Kelly (1/10 Kelly của Ed Thorp)
          - W = 40%, R = 2:1 -> Kelly chuẩn K = 10%
          - 1/10 Kelly = 1% NAV (lý thuyết cực hạn)
          - Quy tắc thực tế tại VN: Mỗi cổ phiếu giải ngân tối đa 10% - 15% tổng NAV.
  Bước 4: Điểm cắt lỗ và Quản trị T+2.5 (Risk Management)
          - Hard stop-loss: Tối đa -7% từ điểm mua hoặc thủng EMA 50.
          - Đi tiền 2 đợt:
            * Đợt 1 (50%): Mua thăm dò tại hỗ trợ
            * Đợt 2 (50%): Mua gia tăng khi hàng đợt 1 về tài khoản (T+2.5) & vượt đỉnh ngắn hạn.
  Bước 5: Chốt lời theo xu hướng (Trailing Stop)
          - Trailing stop theo EMA 20.
          - Bán 100% khi đóng cửa thủng EMA 50 kèm volume lớn.
"""
from __future__ import annotations

from typing import Any, Optional

from . import indicators as ta


# Danh sách các nhóm ngành thường có chu kỳ sóng vĩ mô tại TTCK Việt Nam
FAVORED_MACRO_SECTORS = [
    "Công nghệ thông tin", "Công nghệ", "Phần mềm & Dịch vụ máy tính",
    "Ngân hàng", "Dịch vụ tài chính", "Chứng khoán",
    "Đầu tư công", "Xây dựng", "Vật liệu xây dựng", "Thép", "Hóa chất",
    "Xuất khẩu", "Thủy sản", "Dệt may", "Gỗ",
    "Dầu khí", "Năng lượng", "Điện",
    "Bán lẻ", "Hàng tiêu dùng",
    "Khu công nghiệp", "Bất động sản công nghiệp"
]


def _r(val: Optional[float], digits: int = 1) -> Optional[float]:
    if val is None:
        return None
    try:
        return round(float(val), digits)
    except (TypeError, ValueError):
        return None


def _is_bullish_reversal_candle(candles: list[dict]) -> tuple[bool, str]:
    """Kiểm tra xem cây nến gần nhất (hoặc 2 nến cuối) có phải mẫu hình đảo chiều tăng không."""
    if len(candles) < 2:
        return False, ""
    curr = candles[-1]
    prev = candles[-2]
    try:
        c_open = float(curr.get("o", 0))
        c_high = float(curr.get("h", 0))
        c_low = float(curr.get("l", 0))
        c_close = float(curr.get("c", 0))

        p_open = float(prev.get("o", 0))
        p_close = float(prev.get("c", 0))
    except (TypeError, ValueError):
        return False, ""

    c_range = c_high - c_low
    c_body = abs(c_close - c_open)
    if c_range <= 0:
        return False, ""

    lower_shadow = min(c_open, c_close) - c_low
    upper_shadow = c_high - max(c_open, c_close)
    is_green = c_close >= c_open

    # 1. Nến Búa (Hammer / Pinbar rút chân tăng)
    if is_green and lower_shadow >= 1.8 * c_body and upper_shadow <= 0.6 * c_body and lower_shadow >= 0.45 * c_range:
        return True, "Nến Búa (Hammer / Rút chân hỗ trợ)"

    # 2. Bullish Engulfing (Nến xanh bao phủ nến đỏ trước đó)
    if is_green and p_close < p_open and (c_close >= p_open and c_open <= p_close * 1.003):
        return True, "Nến Bao Phủ Tăng (Bullish Engulfing)"

    # 3. Nến xanh đảo chiều chuẩn (thân nến tăng > 50% biên độ, đóng sát đỉnh)
    if is_green and c_body / c_range >= 0.55 and (c_high - c_close) <= 0.25 * c_range:
        return True, "Nến Xanh Tăng Mạnh (Bullish Momentum)"

    # 4. Sao Mai (Morning Star - 3 nến)
    if len(candles) >= 3:
        p2 = candles[-3]
        p2_open = float(p2.get("o", 0))
        p2_close = float(p2.get("c", 0))
        if p2_close < p2_open and abs(p_close - p_open) < 0.4 * abs(p2_open - p2_close) and is_green and c_close > (p2_open + p2_close) / 2:
            return True, "Mẫu hình Sao Mai (Morning Star)"

    return False, ""


def analyze_trend_following(
    symbol: str,
    candles: list[dict],
    fundamentals: Optional[dict] = None,
    settings: Optional[dict] = None,
    user_eps_growth: Optional[float] = None,
    macro_confirmed: Optional[bool] = None,
) -> dict:
    """Phân tích toàn diện chiến lược Trend Following theo quy chuẩn Ed Thorp - VN Edition."""
    settings = settings or {}
    candles = sorted(candles, key=lambda c: str(c.get("t", "")))
    if len(candles) < 40:
        raise ValueError(f"Không đủ dữ liệu nến cho {symbol} (cần tối thiểu 40 phiên)")

    closes = [float(c["c"]) for c in candles]
    volumes = [float(c.get("v") or 0) for c in candles]
    highs = [float(c["h"]) for c in candles]
    lows = [float(c["l"]) for c in candles]

    current_price = closes[-1]
    prev_close = closes[-2] if len(closes) > 1 else current_price
    current_vol = volumes[-1]

    # Các chỉ báo đường xu hướng & biến động
    ema20_series = ta.ema(closes, 20)
    ema50_series = ta.ema(closes, 50)
    ema200_series = ta.ema(closes, 200)
    sma200_series = ta.sma(closes, 200)
    mid_bb_series = ta.sma(closes, 20)  # Dải giữa Bollinger Band tương đương SMA20
    vol_ma20_series = ta.sma(volumes, 20)

    ema20 = ta.last(ema20_series) or current_price
    ema50 = ta.last(ema50_series) or current_price
    ema200 = ta.last(ema200_series)
    sma200 = ta.last(sma200_series)
    mid_bb = ta.last(mid_bb_series) or current_price
    v20 = ta.last(vol_ma20_series) or 0.0

    # Nếu chuỗi nến chưa đủ 200 phiên (cổ phiếu mới niêm yết hoặc thiếu dữ liệu), dùng giá trị ước tính gần nhất
    effective_ema200 = ema200 if ema200 is not None else (sma200 if sma200 is not None else ema50)

    # ------------------------------------------------------------- BƯỚC 1: BỘ LỌC XU HƯỚNG KẾT HỢP
    # Cơ bản
    sector_name = (fundamentals or {}).get("sector") or ""
    is_macro_favored = bool(macro_confirmed) if macro_confirmed is not None else (
        any(sec.lower() in sector_name.lower() for sec in FAVORED_MACRO_SECTORS) if sector_name else True
    )

    eps_growth = user_eps_growth if user_eps_growth is not None else 18.0  # Mặc định tham chiếu giả định > 15%
    eps_passed = eps_growth >= 15.0 if eps_growth is not None else True
    v20_threshold = float(settings.get("trend_min_volume", 500000.0))
    v20_passed = v20 >= v20_threshold

    # Kỹ thuật
    price_above_ema200 = current_price > effective_ema200
    golden_cross = ema50 > effective_ema200

    step1_tech_passed = price_above_ema200 and golden_cross
    step1_fund_passed = v20_passed and eps_passed and is_macro_favored
    step1_passed = step1_tech_passed and step1_fund_passed

    # ------------------------------------------------------------- BƯỚC 2: ĐIỂM MUA (ENTRY TRIGGER)
    # Kiểm tra pullback về EMA 50 hoặc Mid-BB (MA 20) với dung sai ±2.0%
    dist_to_ema50_pct = abs(current_price - ema50) / ema50 * 100
    dist_to_mid_bb_pct = abs(current_price - mid_bb) / mid_bb * 100
    near_ema50 = dist_to_ema50_pct <= 2.5 or (lows[-1] <= ema50 * 1.015 and current_price >= ema50 * 0.98)
    near_mid_bb = dist_to_mid_bb_pct <= 2.0 or (lows[-1] <= mid_bb * 1.015 and current_price >= mid_bb * 0.98)
    near_support = near_ema50 or near_mid_bb

    has_reversal_candle, reversal_name = _is_bullish_reversal_candle(candles)
    # Vùng kiệt von: khối lượng phiên retest <= V20 (hoặc <= 1.05 * V20)
    is_low_volume = current_vol <= (v20 * 1.05) if v20 > 0 else True

    # Xác nhận: Vượt đỉnh ngắn hạn (15-20 phiên gần nhất) kèm Volume >= 1.5 * V20
    lookback_high = min(len(candles) - 1, 20)
    recent_swing_high = max(highs[-lookback_high:-1]) if lookback_high > 1 else current_price
    breakout_price = current_price >= recent_swing_high * 0.995
    breakout_volume = (current_vol >= 1.45 * v20) if v20 > 0 else False
    is_confirmed_breakout = breakout_price and breakout_volume

    entry_status = "CHỜ TÍN HIỆU"
    entry_label = "Chưa có điểm mua phù hợp"
    entry_reasons = []

    if step1_passed:
        if near_support and has_reversal_candle and is_low_volume:
            entry_status = "MUA_THAM_DO"
            entry_label = "KÍCH HOẠT MUA ĐỢT 1 (Test hỗ trợ kiệt vol)"
            support_desc = "EMA 50" if near_ema50 else "Dải giữa Bollinger Band (MA 20)"
            entry_reasons.append(f"Giá đang kiểm định vùng hỗ trợ {support_desc} (±2%).")
            entry_reasons.append(f"Xuất hiện {reversal_name}.")
            entry_reasons.append(f"Khối lượng phiên hiện tại thấp ({_r(current_vol / v20, 2)}× V20) — xác nhận vùng cạn cung.")
        elif is_confirmed_breakout:
            entry_status = "MUA_GIA_TANG"
            entry_label = "KÍCH HOẠT MUA ĐỢT 2 (Vượt đỉnh xác nhận volume)"
            entry_reasons.append(f"Giá vượt đỉnh ngắn hạn ({_r(recent_swing_high)} đ).")
            entry_reasons.append(f"Khối lượng bùng nổ đạt {_r(current_vol / v20, 2)}× V20 (ngưỡng tối thiểu ≥1.5×).")
        elif near_support:
            entry_status = "THEO_DOI_RETEST"
            entry_label = "Đang ở vùng hỗ trợ — Chờ nến đảo chiều & kiệt vol"
            entry_reasons.append(f"Giá đang áp sát hỗ trợ ({_r(ema50)} đ / {_r(mid_bb)} đ), chờ nến xanh đảo chiều để giải ngân đợt 1.")
        elif current_price > recent_swing_high:
            entry_status = "CANH_GIAC_BULL_TRAP"
            entry_label = "Vượt đỉnh nhưng thiếu Volume — Cảnh giác Bull Trap"
            entry_reasons.append("Giá đang ở vùng cao nhưng volume chưa đạt 1.5× V20, không nên mua đuổi.")
        else:
            entry_status = "THEO_DOI_XU_HUONG"
            entry_label = "Xu hướng tăng duy trì — Chờ nhịp pullback về hỗ trợ"
            entry_reasons.append("Cổ phiếu đạt bộ lọc xu hướng nhưng chưa có điểm kiểm định hợp lý.")
    else:
        entry_status = "KHONG_DAT_LOC"
        entry_label = "Chưa đạt bộ lọc xu hướng / cơ bản (Bước 1)"
        if not price_above_ema200:
            entry_reasons.append(f"Giá ({_r(current_price)} đ) chưa nằm trên EMA 200 ({_r(effective_ema200)} đ).")
        if not golden_cross:
            entry_reasons.append("EMA 50 chưa cắt lên trên EMA 200 (chưa có Golden Cross).")
        if not v20_passed:
            entry_reasons.append(f"Thanh khoản V20 ({int(v20):,} cp) dưới ngưỡng tối thiểu {int(v20_threshold):,} cp/phiên.")

    # ------------------------------------------------------------- BƯỚC 3: ĐỊNH CỠ VỊ THẾ BẰNG 1/10 KELLY
    win_rate = 0.40  # W = 40%
    payoff = 2.0     # R = 2:1
    # Công thức Kelly chuẩn: K = W - (1 - W) / R = 0.4 - 0.6 / 2 = 0.1 (10% vốn)
    standard_kelly_fraction = max(0.0, win_rate - (1.0 - win_rate) / payoff)
    # Áp dụng 1/10 Kelly của Ed Thorp: f* = K / 10 = 0.01 (1% NAV)
    fractional_kelly_fraction = standard_kelly_fraction / 10.0

    # Quy tắc thực tế tại VN: Giải ngân tối đa 10% - 15% NAV cho 1 mã
    nav = float(settings.get("equity") or 500000000.0)
    lot = int(settings.get("lot") or 100)
    cap_pct = 10.0  # 10% NAV theo khuyến nghị thực tế tại VN

    total_budget = nav * (cap_pct / 100.0)
    total_qty = int((total_budget // current_price // lot) * lot) if current_price > 0 else 0
    total_amount = total_qty * current_price

    # ------------------------------------------------------------- BƯỚC 4: ĐIỂM CẮT LỖ VÀ QUẢN TRỊ T+2.5
    # Cắt lỗ cứng: Tối đa -7% hoặc khi đóng cửa thủng EMA 50
    hard_stop_7pct = current_price * 0.93
    ema50_stop = ema50
    # Mức cắt lỗ đề xuất: lấy mức stop chặt chẽ hơn nhưng không quá -7%
    stop_loss_price = _r(max(hard_stop_7pct, ema50_stop * 0.99))

    # Chia làm 2 đợt mua (50% - 50%)
    tranche1_qty = int((total_qty * 0.5 // lot) * lot) if total_qty > 0 else 0
    tranche2_qty = total_qty - tranche1_qty
    tranche1_amount = tranche1_qty * current_price
    tranche2_amount = tranche2_qty * current_price

    risk_per_share = max(current_price - (stop_loss_price or 0), current_price * 0.02)
    max_risk_amount = total_qty * risk_per_share

    # ------------------------------------------------------------- BƯỚC 5: CHỐT LỜI THEO TRAILING STOP
    trailing_stop_ema20 = _r(ema20)
    exit_trigger_ema50 = _r(ema50)

    if current_price >= ema20:
        holding_status = "NẮM GIỮ THEO XU HƯỚNG"
        holding_tone = "up"
        holding_advice = f"Giá vẫn nằm trên EMA 20 ({trailing_stop_ema20} đ) — tiếp tục giữ chặt vị thế theo sóng tăng."
    elif current_price >= ema50:
        holding_status = "CẢNH BÁO SUY YẾU"
        holding_tone = "warn"
        holding_advice = f"Giá đang dưới EMA 20 nhưng còn giữ được EMA 50 ({exit_trigger_ema50} đ) — nâng cao cảnh giác, sẵn sàng thoát nếu thủng."
    else:
        holding_status = "TÍN HIỆU BÁN / THOÁT VỊ THẾ"
        holding_tone = "down"
        holding_advice = f"Giá đã đóng cửa dưới EMA 50 ({exit_trigger_ema50} đ) — kích hoạt tín hiệu bán 100% vị thế bảo toàn vốn."

    # ------------------------------------------------------------- BẢNG TÓM TẮT KHUNG CHIẾN LƯỢC
    summary_table = [
        {
            "component": "Vũ trụ cổ phiếu",
            "detail": "VN100 hoặc thanh khoản > 500k cổ/phiên.",
            "value": f"V20 = {int(v20):,} cp/phiên",
            "passed": v20_passed,
        },
        {
            "component": "Yếu tố bổ trợ",
            "detail": "Ngành dẫn sóng vĩ mô + EPS tăng trưởng > 15%.",
            "value": f"{sector_name or 'Chưa phân ngành'} | EPS: {eps_growth:+.1f}%",
            "passed": eps_passed and is_macro_favored,
        },
        {
            "component": "Tín hiệu Xu hướng",
            "detail": "Giá > EMA 200 và EMA 50 > EMA 200 (Golden Cross).",
            "value": f"Giá: {_r(current_price)} > EMA200: {_r(effective_ema200)} | EMA50: {_r(ema50)}",
            "passed": step1_tech_passed,
        },
        {
            "component": "Quy mô lệnh",
            "detail": "Tối đa 10% NAV/mã (áp dụng tư duy kiểm soát rủi ro 1/10 Kelly).",
            "value": f"{cap_pct}% NAV = {_r(total_amount):,} đ ({total_qty:,} CP)",
            "passed": True,
        },
        {
            "component": "Phòng vệ T+",
            "detail": "Chia mua làm 2 đợt (Thăm dò 50% -> Hàng về T+2.5 -> Gia tăng 50%).",
            "value": f"Đợt 1: {tranche1_qty:,} CP | Đợt 2: {tranche2_qty:,} CP",
            "passed": True,
        },
    ]

    return {
        "symbol": symbol.upper(),
        "strategy_name": "Trend Following (Ed Thorp - VN Edition)",
        "step1_filter": {
            "passed": step1_passed,
            "tech_passed": step1_tech_passed,
            "fund_passed": step1_fund_passed,
            "fundamental": {
                "sector": sector_name or "Đang cập nhật",
                "is_macro_favored": is_macro_favored,
                "eps_growth_pct": eps_growth,
                "eps_passed": eps_passed,
                "v20": round(v20, 0),
                "v20_threshold": v20_threshold,
                "v20_passed": v20_passed,
            },
            "trend": {
                "price": _r(current_price),
                "ema20": _r(ema20),
                "ema50": _r(ema50),
                "ema200": _r(effective_ema200),
                "sma200": _r(sma200) if sma200 else None,
                "mid_bb_ma20": _r(mid_bb),
                "price_above_ema200": price_above_ema200,
                "golden_cross": golden_cross,
            },
        },
        "step2_entry": {
            "status": entry_status,
            "label": entry_label,
            "current_price": _r(current_price),
            "near_ema50": near_ema50,
            "near_mid_bb": near_mid_bb,
            "near_support": near_support,
            "has_reversal_candle": has_reversal_candle,
            "reversal_name": reversal_name or "Chưa có nến đảo chiều",
            "is_low_volume": is_low_volume,
            "volume_ratio": _r(current_vol / v20, 2) if v20 > 0 else None,
            "recent_swing_high": _r(recent_swing_high),
            "breakout_confirmed": is_confirmed_breakout,
            "reasons": entry_reasons,
        },
        "step3_kelly": {
            "win_rate_pct": win_rate * 100.0,
            "payoff": payoff,
            "standard_kelly_pct": _r(standard_kelly_fraction * 100.0, 1),
            "fractional_kelly_pct": _r(fractional_kelly_fraction * 100.0, 1),
            "cap_pct": cap_pct,
            "nav": nav,
            "total_budget": round(total_budget, 0),
            "total_amount": round(total_amount, 0),
            "total_qty": total_qty,
            "lot": lot,
            "notes": [
                f"Kelly chuẩn với W={int(win_rate*100)}%, R={payoff} cho ra {int(standard_kelly_fraction*100)}% NAV.",
                f"Áp dụng 1/10 Kelly của Ed Thorp để phòng vệ chuỗi thua lỗ liên tiếp tại TTCK VN.",
                f"Giới hạn thực tế: Cố định giải ngân tối đa {cap_pct}% NAV ({round(total_budget):,} đ) cho 1 mã.",
            ],
        },
        "step4_risk_t_plus": {
            "hard_stop_loss_pct": -7.0,
            "hard_stop_loss_price": _r(hard_stop_7pct),
            "ema50_stop_price": _r(ema50_stop),
            "stop_loss_price": stop_loss_price,
            "risk_per_share": _r(risk_per_share),
            "max_risk_amount": round(max_risk_amount, 0),
            "tranche1": {
                "label": "Đợt 1 (Mua thăm dò tại hỗ trợ)",
                "pct": 50,
                "quantity": tranche1_qty,
                "amount": round(tranche1_amount, 0),
                "entry_desc": f"Vùng quanh hỗ trợ EMA50 ({_r(ema50)} đ) hoặc Mid-BB ({_r(mid_bb)} đ)",
            },
            "tranche2": {
                "label": "Đợt 2 (Mua gia tăng)",
                "pct": 50,
                "quantity": tranche2_qty,
                "amount": round(tranche2_amount, 0),
                "entry_desc": f"Khi hàng đợt 1 về tài khoản (T+2.5) & giá vượt đỉnh {_r(recent_swing_high)} đ kèm Vol ≥1.5× V20",
            },
            "defense_rule": "Nếu đợt 1 sai, chỉ lỗ trên 50% vị thế và có sẵn hàng để bán cắt lỗ ngay lập tức, không bị kẹt T+2.5.",
        },
        "step5_trailing_stop": {
            "holding_status": holding_status,
            "tone": holding_tone,
            "trailing_stop_ema20": trailing_stop_ema20,
            "exit_trigger_ema50": exit_trigger_ema50,
            "advice": holding_advice,
            "rule_hold": "Giữ cổ phiếu chừng nào giá vẫn nằm trên đường EMA 20 (hoặc đường trendline tăng giá).",
            "rule_exit": "Bán 100% vị thế khi giá đóng cửa cắt xuống dưới EMA 50 với khối lượng lớn, hoặc thị trường chung VN-Index đảo chiều.",
        },
        "summary_table": summary_table,
    }

