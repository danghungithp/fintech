"""Market data service: candle/fundamental caching on top of the Vietcap client."""
from __future__ import annotations

from datetime import datetime, timedelta

from . import db, vietcap
from .config import FUNDAMENTALS_REFRESH_HOURS, SYMBOLS_REFRESH_HOURS


def _hours_since(timestamp: str | None) -> float:
    if not timestamp:
        return 1e9
    try:
        parsed = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return 1e9
    return (datetime.now() - parsed).total_seconds() / 3600.0


def get_candles(symbol: str, days: int = 400, *, force: bool = False,
                cache_hours: float = 6) -> tuple[list[dict], str]:
    """Cached candle history. Returns (candles, source) with source in {'cache','vietcap'}."""
    symbol = symbol.strip().upper()
    cached = db.load_candles(symbol, limit=max(days, 260))
    stats = db.candle_stats(symbol)
    if not force and cached and stats and len(cached) >= min(days, 250):
        updated_at = db.load_cache_stamp(symbol)
        if _hours_since(updated_at) <= cache_hours:
            return cached, "cache"
    try:
        fetched = vietcap.fetch_history(symbol, count=max(days, 260))
    except vietcap.VietcapError:
        if cached:
            return cached, "cache"
        raise
    if not fetched:
        if cached:
            return cached, "cache"
        raise ValueError(f"Không lấy được dữ liệu giá cho {symbol}")
    db.save_candles(symbol, fetched)
    db.save_cache_stamp(symbol)
    merged = db.load_candles(symbol, limit=max(days, 260))
    return merged, "vietcap"


def get_fundamentals(symbol: str, *, force: bool = False, with_events: bool = True) -> dict | None:
    """Cached company fundamentals (dividend TTM, market cap, rating...)."""
    symbol = symbol.strip().upper()
    cached = db.load_fundamentals(symbol)
    if not force and cached and _hours_since(cached.get("updated_at")) <= FUNDAMENTALS_REFRESH_HOURS:
        return cached
    try:
        details = vietcap.fetch_company_details(symbol)
    except vietcap.VietcapError:
        return cached
    if not details:
        return cached
    data = {
        "div_ps_ttm": _safe_float(details.get("dividendPerShareTsr")),
        "market_cap": _safe_float(details.get("marketCap")),
        "rating": details.get("rating"),
        "target_price": _safe_float(details.get("targetPrice")),
        "sector": details.get("sectorVn") or details.get("sector"),
        "rev_growth_qoq": _safe_float(details.get("revenueGrowthQoQ")),
        "rev_growth_yoy": _safe_float(details.get("revenueGrowthYoY")),
        "profit_growth_qoq": _safe_float(details.get("profitGrowthQoQ")),
        "profit_growth_yoy": _safe_float(details.get("profitGrowthYoY")),
        "extra": {
            "issue_share": _safe_float(details.get("issueShare")),
            "foreign_pct": _safe_float(details.get("foreignerPercentage")),
            "profile": (details.get("viOrganName") or "").strip() or None,
        },
    }
    db.save_fundamentals(symbol, data)
    if with_events:
        try:
            events = vietcap.fetch_dividend_events(symbol, years=3)
            if events:
                db.save_dividend_events(symbol, events)
        except vietcap.VietcapError:
            pass
    return db.load_fundamentals(symbol)


def dividend_events(symbol: str, limit: int = 8) -> list[dict]:
    events = db.load_dividend_events(symbol, limit=limit)
    if not events:
        try:
            fetched = vietcap.fetch_dividend_events(symbol, years=3)
            if fetched:
                db.save_dividend_events(symbol, fetched)
                events = db.load_dividend_events(symbol, limit=limit)
        except vietcap.VietcapError:
            pass
    return events


def refresh_symbol_list(force: bool = False) -> int:
    """Download the full Vietcap listing into InfluxDB (throttled)."""
    stats = db.symbol_stats()
    if not force and stats and stats["n"] and _hours_since(stats.get("updated")) <= SYMBOLS_REFRESH_HOURS:
        return 0
    records = vietcap.fetch_vietnam_listings()
    return db.save_symbols(records)


def symbol_search(term: str, limit: int = 20) -> list[dict]:
    try:
        refresh_symbol_list()
    except (vietcap.VietcapError, OSError):
        pass
    return db.search_symbols(term, limit=limit)


def lookup_symbol(symbol: str) -> dict:
    """Symbol metadata with a live fallback when the local cache is empty."""
    symbol = symbol.strip().upper()
    meta = db.symbol_meta(symbol)
    if meta:
        return meta
    try:
        records = vietcap.fetch_vietnam_listings()
        db.save_symbols(records)
        meta = db.symbol_meta(symbol)
    except (vietcap.VietcapError, OSError):
        meta = None
    return meta or {"symbol": symbol, "exchange": "", "organ_name": None, "organ_short_name": None}


def index_summary() -> list[dict]:
    """Latest close + change for VNINDEX and VN30."""
    out = []
    for code in ("VNINDEX", "VN30"):
        try:
            candles, _ = get_candles(code, days=120, cache_hours=6)
        except (vietcap.VietcapError, ValueError, OSError):
            out.append({"symbol": code, "price": None, "change_pct": None, "spark": []})
            continue
        closes = [c["c"] for c in candles]
        price = closes[-1] if closes else None
        change = ((closes[-1] - closes[-2]) / closes[-2] * 100) if len(closes) > 1 else None
        out.append(
            {
                "symbol": code,
                "price": round(price, 2) if price is not None else None,
                "change_pct": round(change, 2) if change is not None else None,
                "spark": [round(c, 2) for c in closes[-60:]],
            }
        )
    return out


def _safe_float(value) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
