"""Quick probe of Vietcap public APIs to verify response shapes (dev utility)."""
import json
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9,vi-VN;q=0.8,vi;q=0.7",
    "Content-Type": "application/json",
    "Cache-Control": "no-cache",
    "Referer": "https://trading.vietcap.com.vn/",
    "Origin": "https://trading.vietcap.com.vn",
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36",
}


def get(url, timeout=20):
    with urlopen(Request(url, headers=HEADERS), timeout=timeout) as r:
        return json.load(r)


def post(url, payload, timeout=20):
    data = json.dumps(payload).encode()
    with urlopen(Request(url, data=data, headers=HEADERS, method="POST"), timeout=timeout) as r:
        return json.load(r)


def probe(name, fn):
    print("=" * 20, name, "=" * 20)
    try:
        result = fn()
        print(json.dumps(result, ensure_ascii=False)[:1800])
    except Exception as exc:  # noqa: BLE001
        print("ERROR:", type(exc).__name__, exc)


def listing():
    data = get("https://trading.vietcap.com.vn/api/price/symbols/getAll")
    rows = data.get("data") if isinstance(data, dict) else data
    return {"count": len(rows), "first": rows[:3]}


def group_vn30():
    data = get("https://trading.vietcap.com.vn/api/price/symbols/getByGroup?" + urlencode({"group": "VN30"}))
    rows = data.get("data") if isinstance(data, dict) else data
    return {"count": len(rows), "first": rows[:3]}


def group_hnx():
    data = get("https://trading.vietcap.com.vn/api/price/symbols/getByGroup?" + urlencode({"group": "HNX"}))
    rows = data.get("data") if isinstance(data, dict) else data
    return {"count": len(rows), "first": rows[:3]}


def chart_fpt():
    payload = {"timeFrame": "ONE_DAY", "symbols": ["FPT"], "to": int(time.time()), "countBack": 5}
    data = post("https://trading.vietcap.com.vn/api/chart/OHLCChart/gap-chart", payload)
    inner = data.get("data") if isinstance(data, dict) else data
    entry = inner[0] if inner else {}
    keys = list(entry.keys()) if isinstance(entry, dict) else []
    sample = {}
    for key in keys:
        value = entry.get(key)
        if isinstance(value, list):
            sample[key] = value[-3:]
        else:
            sample[key] = value
    return {"keys": keys, "sample": sample}


def events_div():
    url = (
        "https://iq.vietcap.com.vn/api/iq-insight-service/v1/events"
        f"?ticker=FPT&fromDate=20230101&toDate={time.strftime('%Y%m%d')}&eventCode=DIV&page=0&size=5"
    )
    data = get(url)
    inner = data.get("data") if isinstance(data, dict) else data
    if isinstance(inner, dict):
        content = inner.get("content", [])
        return {"total": inner.get("totalElements"), "first": content[:2]}
    return {"raw": inner[:2]}


def details_fpt():
    url = "https://iq.vietcap.com.vn/api/iq-insight-service/v1/company/details?ticker=FPT"
    data = get(url)
    inner = data.get("data") if isinstance(data, dict) else data
    if isinstance(inner, dict):
        keys = sorted(inner.keys())
        return {"keys": keys, "dividend_fields": {k: inner[k] for k in keys if "div" in k.lower()}}
    return {"raw": str(inner)[:500]}


def group_probe(name):
    def inner():
        data = get("https://trading.vietcap.com.vn/api/price/symbols/getByGroup?" + urlencode({"group": name}))
        rows = data.get("data") if isinstance(data, dict) else data
        return {"count": len(rows), "first": [r.get("symbol") for r in rows[:5]]}
    return inner


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "groups":
        for group in ["HOSE", "HSX", "VN100", "HNX30", "UPCOM", "ETF", "VNALL", "BANK", "CK", "BDS", "THEP"]:
            probe(f"group {group}", group_probe(group))
    else:
        probe("listing", listing)
        probe("group VN30", group_vn30)
        probe("group HNX", group_hnx)
        probe("chart FPT", chart_fpt)
        probe("events DIV FPT", events_div)
        probe("details FPT", details_fpt)
