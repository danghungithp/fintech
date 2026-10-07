---
kind: external_dependency
name: Vietcap Market Data API (Vietnamese Equities)
slug: vietcap
category: external_dependency
category_hints:
    - sdk_real_api
    - auth_protocol
scope:
    - '**'
---

### Vietcap
- Role: sole source of OHLCV candles, symbol listings, group membership, company fundamentals and cash-dividend events for Vietnamese equities (HOSE/HNX/UPCOM) and indices (VNINDEX, VN30).
- Endpoints used:
  - `GET https://trading.vietcap.com.vn/api/price/symbols/getAll` — full listing
  - `GET https://trading.vietcap.com.vn/api/price/symbols/getByGroup?group=<code>` — symbols by group (VN30/VN100/HNX30/HOSE/HNX/UPCOM/ETF)
  - `POST https://trading.vietcap.com.vn/api/chart/OHLCChart/gap-chart` — OHLC candles (payload: `{timeFrame, symbols[], to, countBack}`)
  - `GET https://iq.vietcap.com.vn/api/iq-insight-service/v1/company/details?ticker=` — fundamentals / TTM dividend/share
  - `GET https://iq.vietcap.com.vn/api/iq-insight-service/v1/events?eventCode=DIV&fromDate=...&toDate=...&page=0&size=50` — cash dividends
- Auth: no token; relies on browser-like headers (`Referer`, `Origin`, `User-Agent`) pointing at `https://trading.vietcap.com.vn/`.
- Concurrency: capped at 6 parallel requests via a module-level semaphore; retry with exponential backoff (3 attempts, 0.6s base).
- Stable shape: payloads are wrapped in a top-level `data` field; response schema differs between list-of-lists vs list-of-dicts candle formats — client normalizes both.
- Timezone: timestamps interpreted as UTC+7 (`ICT`).
- Verify exact payload/response shapes against official Vietcap docs before changing endpoints.