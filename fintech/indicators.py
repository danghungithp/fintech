"""Technical indicators (pure Python, None-padded arrays aligned to input)."""
from __future__ import annotations

import math
from typing import Optional

Num = Optional[float]


def _clean(values: list) -> list[float]:
    return [float(v) if v is not None else float("nan") for v in values]


def sma(values: list, period: int) -> list[Num]:
    out: list[Num] = [None] * len(values)
    if period <= 0:
        return out
    running = 0.0
    count = 0
    for i, value in enumerate(values):
        if value is None or (isinstance(value, float) and math.isnan(value)):
            running = 0.0
            count = 0
            continue
        running += float(value)
        count += 1
        if count > period:
            running -= float(values[i - period])
            count = period
        if count == period:
            out[i] = running / period
    return out


def ema(values: list, period: int) -> list[Num]:
    out: list[Num] = [None] * len(values)
    if period <= 0:
        return out
    multiplier = 2.0 / (period + 1)
    prev: Num = None
    seed: list[float] = []
    for i, value in enumerate(values):
        if value is None or (isinstance(value, float) and math.isnan(value)):
            continue
        current = float(value)
        if prev is None:
            seed.append(current)
            if len(seed) == period:
                prev = sum(seed) / period
                out[i] = prev
        else:
            prev = (current - prev) * multiplier + prev
            out[i] = prev
    return out


def rsi(closes: list, period: int = 14) -> list[Num]:
    """Wilder's RSI."""
    n = len(closes)
    out: list[Num] = [None] * n
    if n <= period:
        return out
    gains = 0.0
    losses = 0.0
    for i in range(1, period + 1):
        delta = float(closes[i]) - float(closes[i - 1])
        gains += max(delta, 0.0)
        losses += max(-delta, 0.0)
    avg_gain = gains / period
    avg_loss = losses / period
    out[period] = 100.0 if avg_loss == 0 else 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)
    for i in range(period + 1, n):
        delta = float(closes[i]) - float(closes[i - 1])
        avg_gain = (avg_gain * (period - 1) + max(delta, 0.0)) / period
        avg_loss = (avg_loss * (period - 1) + max(-delta, 0.0)) / period
        out[i] = 100.0 if avg_loss == 0 else 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)
    return out


def macd(closes: list, fast: int = 12, slow: int = 26, signal_period: int = 9):
    """Returns (macd_line, signal_line, histogram)."""
    fast_ema = ema(closes, fast)
    slow_ema = ema(closes, slow)
    line: list[Num] = [
        (fast_ema[i] - slow_ema[i]) if (fast_ema[i] is not None and slow_ema[i] is not None) else None
        for i in range(len(closes))
    ]
    signal_line = ema(line, signal_period)
    histogram: list[Num] = [
        (line[i] - signal_line[i]) if (line[i] is not None and signal_line[i] is not None) else None
        for i in range(len(closes))
    ]
    return line, signal_line, histogram


def true_range(candles: list[dict]) -> list[Num]:
    out: list[Num] = [None] * len(candles)
    for i, bar in enumerate(candles):
        if i == 0:
            out[i] = float(bar["h"]) - float(bar["l"])
            continue
        prev_close = float(candles[i - 1]["c"])
        out[i] = max(
            float(bar["h"]) - float(bar["l"]),
            abs(float(bar["h"]) - prev_close),
            abs(float(bar["l"]) - prev_close),
        )
    return out


def atr(candles: list[dict], period: int = 14) -> list[Num]:
    """Wilder's ATR."""
    tr = true_range(candles)
    out: list[Num] = [None] * len(candles)
    if len(candles) < period:
        return out
    prev = sum(float(x) for x in tr[:period]) / period
    out[period - 1] = prev
    for i in range(period, len(candles)):
        prev = (prev * (period - 1) + float(tr[i])) / period
        out[i] = prev
    return out


def rolling_std(values: list, period: int) -> list[Num]:
    out: list[Num] = [None] * len(values)
    for i in range(period - 1, len(values)):
        window = [float(v) for v in values[i - period + 1: i + 1] if v is not None]
        if len(window) < period:
            continue
        mean = sum(window) / period
        variance = sum((x - mean) ** 2 for x in window) / period
        out[i] = math.sqrt(variance)
    return out


def bollinger(closes: list, period: int = 20, mult: float = 2.0):
    mid = sma(closes, period)
    std = rolling_std(closes, period)
    upper: list[Num] = [
        (mid[i] + mult * std[i]) if (mid[i] is not None and std[i] is not None) else None
        for i in range(len(closes))
    ]
    lower: list[Num] = [
        (mid[i] - mult * std[i]) if (mid[i] is not None and std[i] is not None) else None
        for i in range(len(closes))
    ]
    return upper, mid, lower


def volume_sma(candles: list[dict], period: int = 20) -> list[Num]:
    return sma([float(c.get("v") or 0) for c in candles], period)


def last(seq: list[Num]) -> Num:
    for value in reversed(seq):
        if value is not None:
            return value
    return None


def slope_pct(seq: list[Num], idx: int, lookback: int = 10) -> Num:
    """Percent slope of a series over `lookback` bars ending at idx."""
    if idx - lookback < 0:
        return None
    current = seq[idx]
    base = seq[idx - lookback]
    if current is None or base is None or base == 0:
        return None
    return (current - base) / abs(base) * 100.0
