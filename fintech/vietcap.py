"""Vietcap (VCI) public market data client.

Endpoints (verified live):
  - GET  trading.vietcap.com.vn/api/price/symbols/getAll          -> full listing
  - GET  trading.vietcap.com.vn/api/price/symbols/getByGroup      -> symbols by group
  - POST trading.vietcap.com.vn/api/chart/OHLCChart/gap-chart     -> OHLC candles
  - GET  iq.vietcap.com.vn/api/iq-insight-service/v1/company/details -> fundamentals
  - GET  iq.vietcap.com.vn/api/iq-insight-service/v1/events       -> dividends (DIV)
"""
from __future__ import annotations

import json
import threading
import time
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

_TRADING = "https://trading.vietcap.com.vn/api"
_IQ = "https://iq.vietcap.com.vn/api/iq-insight-service"

_LISTING_URL = f"{_TRADING}/price/symbols/getAll"
_GROUP_URL = f"{_TRADING}/price/symbols/getByGroup"
_CHART_URL = f"{_TRADING}/chart/OHLCChart/gap-chart"
_DETAILS_URL = f"{_IQ}/v1/company/details"
_EVENTS_URL = f"{_IQ}/v1/events"

_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9,vi-VN;q=0.8,vi;q=0.7",
    "Content-Type": "application/json",
    "Cache-Control": "no-cache",
    "Referer": "https://trading.vietcap.com.vn/",
    "Origin": "https://trading.vietcap.com.vn",
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36",
}

_ICT = timezone(timedelta(hours=7))
_MAX_CONCURRENCY = threading.Semaphore(6)


class VietcapError(RuntimeError):
    """Raised when the Vietcap API cannot be reached or returns invalid data."""


def _request(url: str, data: bytes | None = None, timeout: int = 20, retries: int = 3):
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            request = Request(url, data=data, headers=_HEADERS, method="POST" if data else "GET")
            with _MAX_CONCURRENCY:
                with urlopen(request, timeout=timeout) as response:
                    return json.load(response)
        except Exception as exc:  # noqa: BLE001 - retry any transport error
            last_error = exc
            if attempt < retries - 1:
                time.sleep(0.6 * (attempt + 1))
    raise VietcapError(f"Vietcap request failed: {url} ({last_error})")


def _data(payload):
    if isinstance(payload, dict):
        return payload.get("data")
    return payload


def normalize_exchange(board: str | None) -> str:
    value = str(board or "").strip().upper()
    if value in {"HSX", "HOSE"}:
        return "HOSE"
    if value in {"UPX", "UPCOM"}:
        return "UPCOM"
    if value in {"HNX", "HNX30"}:
        return "HNX"
    return value or ""


def fetch_vietnam_listings(timeout: int = 20) -> list[dict]:
    """All listed instruments with exchange/exchange metadata."""
    payload = _data(_request(_LISTING_URL, timeout=timeout))
    if not isinstance(payload, list):
        raise VietcapError("Vietcap listing API returned an unexpected response")
    records = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        records.append(
            {
                "symbol": symbol,
                "exchange": normalize_exchange(item.get("board")),
                "type": str(item.get("type") or "").strip().upper(),
                "organ_name": item.get("organName"),
                "organ_short_name": item.get("organShortName"),
            }
        )
    return records


def fetch_vietcap_group(group: str, timeout: int = 20) -> list[str]:
    """Symbols belonging to a Vietcap trading group (VN30, HOSE, ...)."""
    query = urlencode({"group": str(group).strip().upper()})
    payload = _data(_request(f"{_GROUP_URL}?{query}", timeout=timeout))
    if not isinstance(payload, list):
        raise VietcapError(f"Vietcap group API returned an unexpected response for '{group}'")
    symbols: list[str] = []
    for item in payload:
        if isinstance(item, dict) and item.get("symbol"):
            symbols.append(str(item["symbol"]).strip().upper())
    return symbols


def _parse_timestamp(value, is_intraday: bool = False) -> str | None:
    try:
        ts = float(value)
    except (TypeError, ValueError):
        return None
    if ts > 10**11:  # milliseconds
        ts /= 1000.0
    dt = datetime.fromtimestamp(ts, _ICT)
    return dt.isoformat() if is_intraday else dt.date().isoformat()


def _fallback_dates(count: int) -> list[str]:
    days: list[date] = []
    cursor = datetime.now(_ICT).date()
    while len(days) < count:
        if cursor.weekday() < 5:
            days.append(cursor)
        cursor -= timedelta(days=1)
    return [d.isoformat() for d in reversed(days)]


def fetch_history(symbol: str, count: int = 400, timeframe: str = "ONE_DAY", timeout: int = 25) -> list[dict]:
    """OHLCV candles, oldest first: [{'t','o','h','l','c','v'}, ...].

    Works for stocks (FPT) and indices (VNINDEX, VN30).
    """
    normalized = str(symbol).strip().upper()
    if not normalized:
        raise ValueError("Symbol is required")
    try:
        count = max(1, int(count))
    except (TypeError, ValueError):
        count = 400
    payload = json.dumps(
        {
            "timeFrame": timeframe,
            "symbols": [normalized],
            "to": int(time.time()),
            "countBack": count,
        }
    ).encode("utf-8")
    response = _data(_request(_CHART_URL, data=payload, timeout=timeout))
    entry = response[0] if isinstance(response, list) and response else None
    if not isinstance(entry, dict):
        return []
    columns = ("o", "h", "l", "c", "v")
    if not all(isinstance(entry.get(col), list) for col in columns):
        return []
    try:
        series = [entry[col][-count:] for col in columns]
        length = min(len(s) for s in series)
        opens, highs, lows, closes, volumes = (s[-length:] for s in series)
        raw_times = entry.get("t") or entry.get("time") or []
        dates: list[str] = []
        is_intraday = timeframe not in ("ONE_DAY", "D", "1D")
        if isinstance(raw_times, list) and len(raw_times) >= length:
            dates = [_parse_timestamp(ts, is_intraday=is_intraday) or "" for ts in raw_times[-length:]]
        if len(dates) != length or not all(dates):
            dates = _fallback_dates(length)
        candles = []
        for i in range(length):
            close = float(closes[i])
            if close <= 0:
                continue
            candles.append(
                {
                    "t": dates[i],
                    "o": float(opens[i]),
                    "h": float(highs[i]),
                    "l": float(lows[i]),
                    "c": close,
                    "v": float(volumes[i]),
                }
            )
        return candles
    except (TypeError, ValueError, IndexError) as exc:
        raise VietcapError(f"Invalid candle data for {normalized}: {exc}") from exc


def fetch_company_details(symbol: str, timeout: int = 15) -> dict:
    """Company fundamentals snapshot (dividend TTM, market cap, rating...)."""
    normalized = str(symbol).strip().upper()
    query = urlencode({"ticker": normalized})
    payload = _data(_request(f"{_DETAILS_URL}?{query}", timeout=timeout))
    if not isinstance(payload, dict):
        return {}
    return payload


def fetch_dividend_events(symbol: str, years: int = 3, timeout: int = 15) -> list[dict]:
    """Cash dividend events, newest first: [{'ex_date','amount','title'} ...]."""
    normalized = str(symbol).strip().upper()
    to_date = datetime.now(_ICT).strftime("%Y%m%d")
    from_date = (datetime.now(_ICT) - timedelta(days=365 * max(1, years))).strftime("%Y%m%d")
    query = urlencode(
        {
            "ticker": normalized,
            "fromDate": from_date,
            "toDate": to_date,
            "eventCode": "DIV",
            "page": 0,
            "size": 50,
        }
    )
    payload = _data(_request(f"{_EVENTS_URL}?{query}", timeout=timeout))
    content = []
    if isinstance(payload, dict):
        content = payload.get("content") or []
    elif isinstance(payload, list):
        content = payload
    events: list[dict] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        amount = item.get("valuePerShare")
        try:
            amount = float(amount) if amount is not None else None
        except (TypeError, ValueError):
            amount = None
        if not amount or amount <= 0:
            continue  # only cash dividends carry valuePerShare
        raw_date = item.get("exrightDate") or item.get("recordDate") or item.get("payoutDate")
        ex_date = str(raw_date or "")[:10]
        if not ex_date:
            continue
        events.append(
            {
                "ex_date": ex_date,
                "amount": amount,
                "title": item.get("eventTitleVi") or item.get("eventNameVi") or "Cổ tức tiền mặt",
            }
        )
    events.sort(key=lambda e: e["ex_date"], reverse=True)
    return events


def fetch_index_history(symbol: str, count: int = 100, timeout: int = 25) -> dict:
    """Backwards-compatible index helper (VNINDEX / VN30)."""
    normalized = str(symbol).strip().upper()
    if normalized not in {"VNINDEX", "VN30", "HNXINDEX", "HNXUPCOMINDEX", "UPCOM"}:
        raise ValueError("Only VNINDEX and VN30 index history is supported")
    candles = fetch_history(normalized, count=count, timeout=timeout)
    return {
        "close_prices": [c["c"] for c in candles],
        "volumes": [c["v"] for c in candles],
        "candles": candles,
    }
