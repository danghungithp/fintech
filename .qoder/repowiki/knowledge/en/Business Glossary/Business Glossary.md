---
kind: business_term
name: Business Glossary
category: business_term
scope:
    - '**'
---

### Fibonacci retracement
- Definition：Technical-analysis method applied to OHLC candles to mark buy/sell zones at the golden zone (0.5–0.618) and extensions (1.272/1.618), rendered as overlays on the candlestick chart alongside MUA/BÁN arrows.
- Aliases：fibonacy、fibonacci、Fib

### Pivot Point
- Definition：Support/resistance reference point computed per day/week/month from the prior period's high/low/close, used together with Fibonacci to locate buy/sell zones.
- Aliases：pivot

### MUA/BÁN
- Definition：Vietnamese labels for BUY/SELL signals plotted as arrows on the analysis chart; derived from the internal signal score (-100..100) thresholds defined in config.
- Aliases：mua/bán、buy/sell markers

### Edward Thorp Kelly 1/2
- Definition：Half-Kelly capital-management sizing using `f* = p − q/b` (Thorp variant), clamped by risk-% and max-position %, rounded to 100-share lots; auto-prefilled from backtest win-rate and payoff.
- Aliases：Kelly 1/2、half-Kelly、kelly_mode=half

### Danh mục đầu tư
- Definition：Portfolio management page where users add positions and watchlist entries; feeds the alert engine that scans holdings for buy/sell/cut-loss/take-profit signals.
- Aliases：portfolio

### Cắt lỗ
- Definition：Stop-loss alert type raised when a held position breaches its stop-loss level; classified as a critical alert in the portfolio/alert engine.
- Aliases：stop-loss、cut loss

### Chốt lời
- Definition：Take-profit alert type raised when a position reaches its target price.
- Aliases：take profit

### Screener
- Definition：Universe scanner over VN30/VN100/HNX30/HOSE/HNX/UPCOM/ETF or custom lists that filters by technical signals, minimum score, liquidity, price, and dividend yield ≥ x% of market price; runs in a background thread with live progress and CSV export.
- Aliases：quét cổ phiếu、screening

### Cổ tức ≥ thị giá
- Definition：Dividend-yield filter expressed as a percentage of current market price (e.g. entering `6` means dividend ≥ 6% of price); used in the screener to rank dividend-paying stocks.
- Aliases：dividend yield filter

### Trailing stop >8%
- Definition：Alert triggered when a position falls more than 8% below its peak price during the scan window.
- Aliases：trailing stop

### Thủng hỗ trợ
- Definition：Alert raised when a holding breaks below a computed support level.
- Aliases：support break

### Đạt mục tiêu
- Definition：Alert raised when a position reaches its user-defined target price.
- Aliases：target hit
