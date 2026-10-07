/* FinViet Pro — trading chart renderer (lightweight-charts) */
(function () {
  'use strict';

  const THEME = {
    bg: 'transparent',
    text: '#8ea3c4',
    grid: 'rgba(148, 163, 184, 0.08)',
    border: 'rgba(148, 163, 184, 0.15)',
    up: '#16c784',
    down: '#ef4b5e',
    upWick: '#16c784',
    downWick: '#ef4b5e',
  };

  const COLORS = {
    ma20: '#38bdf8',
    ma50: '#f59e0b',
    ma200: '#a78bfa',
    fib: '#f0b90b',
    fibGolden: '#ffd166',
    pivot: '#64748b',
    support: '#2dd4bf',
    resistance: '#f472b6',
  };

  function baseOptions(extra = {}) {
    return Object.assign({
      layout: {
        background: { type: 'solid', color: THEME.bg },
        textColor: THEME.text,
        fontFamily: "'Inter', sans-serif",
        fontSize: 11,
      },
      grid: {
        vertLines: { color: THEME.grid },
        horzLines: { color: THEME.grid },
      },
      rightPriceScale: { borderColor: THEME.border, scaleMargins: { top: 0.08, bottom: 0.22 } },
      timeScale: { borderColor: THEME.border, timeVisible: false, rightOffset: 4, barSpacing: 7 },
      crosshair: {
        mode: 0,
        vertLine: { color: 'rgba(56,189,248,0.35)', labelBackgroundColor: '#1e3a8a' },
        horzLine: { color: 'rgba(56,189,248,0.35)', labelBackgroundColor: '#1e3a8a' },
      },
      localization: {
        locale: 'vi-VN',
        priceFormatter: (p) => (Math.abs(p) >= 1000 ? (p / 1000).toFixed(1) + 'k' : p.toFixed(2)),
      },
      handleScroll: true,
      handleScale: true,
    }, extra);
  }

  function toCandles(payload) {
    return payload.candles.map((c) => ({ time: c.t, open: c.o, high: c.h, low: c.l, close: c.c }));
  }

  function seriesData(list, times) {
    const out = [];
    for (let i = 0; i < times.length; i++) {
      if (list && list[i] !== null && list[i] !== undefined) out.push({ time: times[i], value: list[i] });
    }
    return out;
  }

  /**
   * Render the main price chart with overlays.
   * @param {HTMLElement} container
   * @param {Object} payload - /api/analyze response
   * @param {Object} layerOptions - {fib, pivots, sr, sma, markers, volume}
   */
  function renderPriceChart(container, payload, layerOptions = {}) {
    const LWC = window.LightweightCharts;
    if (!LWC) {
      container.innerHTML = '<div class="empty-state">Không tải được thư viện biểu đồ (cần internet). Bảng số liệu bên phải vẫn hoạt động bình thường.</div>';
      return null;
    }
    container.innerHTML = '';
    const opts = Object.assign({ fib: true, pivots: true, sr: true, sma: true, markers: true, volume: true }, layerOptions);
    const chart = LWC.createChart(container, baseOptions());
    const times = payload.candles.map((c) => c.t);

    const candleSeries = chart.addCandlestickSeries({
      upColor: THEME.up, downColor: THEME.down,
      wickUpColor: THEME.upWick, wickDownColor: THEME.downWick,
      borderVisible: false,
      priceLineVisible: true,
      priceLineColor: 'rgba(148,163,184,0.45)',
      priceLineStyle: 3,
    });
    candleSeries.setData(toCandles(payload));

    if (opts.volume && payload.candles.some((c) => c.v)) {
      const volSeries = chart.addHistogramSeries({
        priceFormat: { type: 'volume' },
        priceScaleId: 'vol',
        lastValueVisible: false,
        priceLineVisible: false,
      });
      chart.priceScale('vol').applyOptions({ scaleMargins: { top: 0.84, bottom: 0 } });
      volSeries.setData(payload.candles.map((c) => ({
        time: c.t,
        value: c.v,
        color: c.c >= c.o ? 'rgba(22,199,132,0.38)' : 'rgba(239,75,94,0.38)',
      })));
    }

    if (opts.sma && payload.sma) {
      const maDefs = [
        ['ma20', COLORS.ma20, 1.4, 'SMA20'],
        ['ma50', COLORS.ma50, 1.4, 'SMA50'],
        ['ma200', COLORS.ma200, 1.4, 'SMA200'],
      ];
      maDefs.forEach(([key, color, width, title]) => {
        const data = seriesData(payload.sma[key], times);
        if (!data.length) return;
        const line = chart.addLineSeries({
          color, lineWidth: width, title,
          priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false,
        });
        line.setData(data);
      });
    }

    const priceLines = [];
    const fib = payload.fib || {};
    if (opts.fib && fib.levels && fib.levels.length) {
      const nearestSupport = fib.nearest_support;
      const nearestResistance = fib.nearest_resistance;
      fib.levels.forEach((lvl) => {
        const isGolden = lvl.ratio === 0.5 || lvl.ratio === 0.618;
        const isNearest = lvl.price === nearestSupport || lvl.price === nearestResistance;
        priceLines.push({
          price: lvl.price,
          color: isGolden ? COLORS.fibGolden : 'rgba(240,185,11,0.45)',
          lineWidth: isNearest ? 2 : 1,
          lineStyle: isGolden ? LWC.LineStyle.Solid : LWC.LineStyle.Dashed,
          title: `Fib ${lvl.ratio}`,
        });
      });
      (fib.extensions || []).forEach((lvl) => {
        priceLines.push({
          price: lvl.price,
          color: 'rgba(99,102,241,0.5)',
          lineWidth: 1,
          lineStyle: LWC.LineStyle.Dotted,
          title: `Ext ${lvl.ratio}`,
        });
      });
    }

    if (opts.pivots && payload.pivots) {
      const daily = payload.pivots.daily || {};
      const pivotDefs = [
        ['p', 'Pivot', 'rgba(148,163,184,0.55)'],
        ['s1', 'S1', 'rgba(45,212,191,0.5)'], ['s2', 'S2', 'rgba(45,212,191,0.35)'],
        ['r1', 'R1', 'rgba(244,114,182,0.5)'], ['r2', 'R2', 'rgba(244,114,182,0.35)'],
      ];
      pivotDefs.forEach(([key, title, color]) => {
        if (daily[key]) {
          priceLines.push({ price: daily[key], color, lineWidth: 1, lineStyle: LWC.LineStyle.Dotted, title });
        }
      });
    }

    if (opts.sr) {
      (payload.supports || []).slice(0, 3).forEach((s) => {
        priceLines.push({
          price: s.price, color: 'rgba(45,212,191,0.7)', lineWidth: 1, lineStyle: LWC.LineStyle.LargeDashed,
          title: `HT ${s.touches}x`,
        });
      });
      (payload.resistances || []).slice(0, 3).forEach((r) => {
        priceLines.push({
          price: r.price, color: 'rgba(244,114,182,0.7)', lineWidth: 1, lineStyle: LWC.LineStyle.LargeDashed,
          title: `KC ${r.touches}x`,
        });
      });
    }

    const levels = payload.levels || {};
    if (levels.buy_zone && levels.buy_zone.length === 2) {
      priceLines.push({
        price: levels.buy_zone[0], color: 'rgba(22,199,132,0.8)', lineWidth: 2, lineStyle: LWC.LineStyle.Solid,
        title: 'VÙNG MUA', axisLabelVisible: false,
      });
      priceLines.push({
        price: levels.buy_zone[1], color: 'rgba(22,199,132,0.8)', lineWidth: 2, lineStyle: LWC.LineStyle.Solid,
        title: 'VÙNG MUA (đỉnh vùng)', axisLabelVisible: false,
      });
    }
    if (levels.stop_loss) {
      priceLines.push({ price: levels.stop_loss, color: '#ef4b5e', lineWidth: 1, lineStyle: LWC.LineStyle.Dashed, title: 'CẮT LỖ' });
    }
    (levels.sell_points || []).slice(0, 2).forEach((sp, idx) => {
      priceLines.push({ price: sp.price, color: 'rgba(167,139,250,0.65)', lineWidth: 1, lineStyle: LWC.LineStyle.Dashed, title: `TP${idx + 1}` });
    });

    priceLines.forEach((line) => {
      try { candleSeries.createPriceLine({ axisLabelVisible: true, ...line }); } catch (e) { /* skip */ }
    });

    if (opts.markers && payload.markers && payload.markers.length) {
      const markers = payload.markers
        .filter((m) => m.t && m.price)
        .sort((a, b) => (a.t < b.t ? -1 : 1))
        .map((m) => ({
          time: m.t,
          position: m.type === 'buy' ? 'belowBar' : 'aboveBar',
          color: m.type === 'buy' ? THEME.up : THEME.down,
          shape: m.type === 'buy' ? 'arrowUp' : 'arrowDown',
          text: m.type === 'buy' ? 'MUA' : 'BÁN',
          size: 1.4,
        }));
      const deduped = [];
      const seen = new Set();
      markers.forEach((m) => {
        if (seen.has(m.time)) return;
        seen.add(m.time);
        deduped.push(m);
      });
      try { candleSeries.setMarkers(deduped); } catch (e) { /* skip */ }
    }

    chart.timeScale().fitContent();
    observeResize(container, chart);
    return { chart, candleSeries };
  }

  function renderRsiChart(container, payload) {
    const LWC = window.LightweightCharts;
    if (!LWC) return null;
    container.innerHTML = '';
    const chart = LWC.createChart(container, baseOptions({
      rightPriceScale: { borderColor: THEME.border, scaleMargins: { top: 0.12, bottom: 0.12 } },
      timeScale: { visible: false },
      crosshair: { mode: 0 },
    }));
    const times = payload.candles.map((c) => c.t);
    const rsiSeries = chart.addLineSeries({
      color: '#f59e0b', lineWidth: 1.6, priceLineVisible: false,
      lastValueVisible: true, title: 'RSI',
      priceFormat: { type: 'price', precision: 0, minMove: 1 },
    });
    rsiSeries.setData(seriesData(payload.rsi_series, times));
    [30, 70].forEach((lvl) => {
      rsiSeries.createPriceLine({
        price: lvl, color: 'rgba(148,163,184,0.4)', lineWidth: 1, lineStyle: LWC.LineStyle.Dashed,
        title: String(lvl), axisLabelVisible: true,
      });
    });
    chart.timeScale().fitContent();
    observeResize(container, chart);
    return { chart, rsiSeries };
  }

  function linkCharts(main, sub) {
    if (!main || !sub) return;
    let syncing = false;
    const link = (from, to) => {
      from.timeScale().subscribeVisibleLogicalRangeChange((range) => {
        if (syncing || !range) return;
        syncing = true;
        try { to.timeScale().setVisibleLogicalRange(range); } catch (e) { /* ignore */ }
        syncing = false;
      });
    };
    link(main.chart, sub.chart);
    link(sub.chart, main.chart);
  }

  function observeResize(container, chart) {
    if (typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(() => {
      // Track both dimensions: if the chart was created while its container was
      // hidden (0x0), this restores the real size as soon as it becomes visible.
      try { chart.applyOptions({ width: container.clientWidth, height: container.clientHeight }); } catch (e) { /* ignore */ }
    });
    ro.observe(container);
  }

  function renderSparkline(container, values, color) {
    if (!values || values.length < 2) { container.innerHTML = ''; return; }
    const w = 74; const h = 26;
    const min = Math.min(...values); const max = Math.max(...values);
    const span = max - min || 1;
    const points = values.map((v, i) => {
      const x = (i / (values.length - 1)) * w;
      const y = h - ((v - min) / span) * (h - 4) - 2;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(' ');
    container.innerHTML = `<svg class="spark" width="${w}" height="${h}"><polyline fill="none" stroke="${color}" stroke-width="1.6" points="${points}"/></svg>`;
  }

  window.Charts = { renderPriceChart, renderRsiChart, linkCharts, renderSparkline };
})();
