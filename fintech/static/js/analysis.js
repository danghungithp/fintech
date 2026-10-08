/* FinViet Pro — analysis page */
(function () {
  'use strict';
  const { fmt, fetchJSON, postJSON, toast, signalBadge } = App;

  const el = (id) => document.getElementById(id);
  let current = null;
  let settings = null;
  let charts = null;

  const FIB_LABELS = { 0.236: 'Fib 23.6%', 0.382: 'Fib 38.2%', 0.5: 'Fib 50% (vàng)', 0.618: 'Fib 61.8% (vàng)', 0.786: 'Fib 78.6%' };

  function showState(state) {
    ['analysis-empty', 'analysis-loading', 'analysis-error', 'analysis-view'].forEach((id) => {
      const node = el(id);
      if (node) node.classList.toggle('hidden', id !== state);
    });
  }

  async function analyze(symbol, refresh = false) {
    symbol = (symbol || '').trim().toUpperCase();
    if (!symbol) { toast('Vui lòng nhập mã cổ phiếu', 'warn'); return; }
    el('symbol-input').value = symbol;
    showState('analysis-loading');
    el('analyze-btn').disabled = true;
    try {
      const payload = await fetchJSON(`/api/analyze?symbol=${encodeURIComponent(symbol)}${refresh ? '&refresh=1' : ''}`);
      current = payload;
      // Show the view BEFORE rendering: chart libraries measure the container at
      // creation time, and a display:none parent yields a 0px-high canvas.
      showState('analysis-view');
      renderAll(payload);
      loadAdvanced(symbol, refresh);
      const url = new URL(window.location.href);
      url.searchParams.set('symbol', symbol);
      window.history.replaceState(null, '', url.toString());
    } catch (err) {
      el('analysis-error').innerHTML = `<strong>Không phân tích được ${fmt.escape(symbol)}</strong>${fmt.escape(err.message)}`;
      showState('analysis-error');
    } finally {
      el('analyze-btn').disabled = false;
    }
  }

  function renderAll(p) {
    renderHeader(p);
    renderChart(p);
    renderSignal(p);
    renderLevels(p);
    prefillKelly(p);
    renderFib(p);
    renderPivot(p);
    renderSupportsResistances(p);
    renderIndicators(p);
    renderBacktest(p);
    renderDividends(p);
  }

  function renderHeader(p) {
    const meta = p.meta || {};
    el('sym-name').textContent = p.symbol + (meta.organ_short_name ? ' — ' + meta.organ_short_name : '');
    el('sym-meta').textContent = [meta.exchange, meta.organ_name].filter(Boolean).join(' · ');
    el('sym-price').textContent = fmt.price(p.price) + ' đ';
    const chg = el('sym-change');
    chg.textContent = fmt.pct(p.change_pct);
    chg.className = 'chg tnum ' + fmt.tone(p.change_pct);
    el('sym-signal').innerHTML = signalBadge(p.signal) + ` <span class="chip">Cập nhật: ${p.updated_at || ''}</span>`;
    el('sym-source').textContent = p.data_source === 'cache' ? 'Nguồn: bộ đệm nội bộ' : 'Nguồn: Vietcap (mới tải)';
  }

  function renderChart(p) {
    charts = {};
    charts.main = Charts.renderPriceChart(el('price-chart'), p);
    charts.rsi = Charts.renderRsiChart(el('rsi-chart'), p);
    if (charts.main && charts.rsi) Charts.linkCharts(charts.main, charts.rsi);
  }

  function renderSignal(p) {
    const sig = p.signal;
    el('signal-label').textContent = sig.label;
    el('signal-label').className = 'gauge-label ' + fmt.tone(sig.score);
    el('signal-bar').innerHTML = App.scoreBar(sig.score);
    el('sym-score-chip').textContent = `Điểm: ${sig.score > 0 ? '+' : ''}${sig.score}`;
    const ind = p.indicators || {};
    el('signal-kv').innerHTML = [
      ['Giá hiện tại', fmt.price(p.price) + ' đ'],
      ['Thay đổi phiên', `<span class="${fmt.tone(p.change_pct)}">${fmt.pct(p.change_pct)}</span>`],
      ['RSI (14)', ind.rsi != null ? ind.rsi : '—'],
      ['KL so với TB20', ind.volume_ratio != null ? ind.volume_ratio + '×' : '—'],
    ].map(([k, v]) => `<div class="kv-row"><span class="k">${k}</span><span class="v">${v}</span></div>`).join('');
    el('signal-reasons').innerHTML = (p.reasons || []).map((r) => `<li>${fmt.escape(r)}</li>`).join('')
      || '<li>Chưa có yếu tố nổi bật</li>';
  }

  function levelItem(cls, label, price) {
    return `<div class="level-item ${cls}"><span class="lbl">${fmt.escape(label)}</span><span class="prc">${fmt.price(price)} đ</span></div>`;
  }

  function renderLevels(p) {
    const lv = p.levels || {};
    el('levels-buy').innerHTML = (lv.buy_points || []).map((b) => levelItem('buy', b.label, b.price)).join('')
      || '<div class="level-item"><span class="lbl">Không có vùng mua rõ ràng — chờ tín hiệu xác nhận</span></div>';
    el('levels-stop').innerHTML = levelItem('stop', 'Cắt lỗ (Stop loss)', lv.stop_loss);
    el('levels-sell').innerHTML = (lv.sell_points || []).map((s) => levelItem('sell', s.label, s.price)).join('')
      || '<div class="level-item"><span class="lbl">Chưa xác định kháng cự gần</span></div>';
    el('levels-rr').textContent = lv.risk_reward != null ? lv.risk_reward + ' lần' : '—';
    el('levels-warnings').innerHTML = (lv.warnings || []).map((w) => `<div class="warn-banner">⚠<span>${fmt.escape(w)}</span></div>`).join('');
  }

  async function loadSettings() {
    if (!settings) settings = await fetchJSON('/api/settings');
    return settings;
  }

  async function prefillKelly(p) {
    let s = {};
    try { s = await loadSettings(); } catch (e) { /* defaults */ }
    el('k-equity').value = s.equity || 500000000;
    el('k-entry').value = p.price || '';
    el('k-stop').value = (p.levels || {}).stop_loss || '';
    const bt = p.backtest || {};
    el('k-win').value = bt.win_rate != null ? bt.win_rate : 50;
    el('k-payoff').value = bt.payoff != null ? bt.payoff : 2;
    el('k-mode').value = s.kelly_mode || 'half';
    el('k-result').classList.add('hidden');
  }

  async function calcKelly() {
    const body = {
      equity: parseFloat(el('k-equity').value),
      entry: parseFloat(el('k-entry').value),
      stop: parseFloat(el('k-stop').value),
      win_prob: parseFloat(el('k-win').value),
      payoff: parseFloat(el('k-payoff').value),
      mode: el('k-mode').value,
    };
    if (!body.entry || !body.stop || body.stop >= body.entry) {
      toast('Giá cắt lỗ phải nhỏ hơn giá vào', 'warn', 'Kelly 1/2'); return;
    }
    try {
      const r = await postJSON('/api/kelly/calc', body);
      const modeLabel = r.mode === 'full' ? 'Kelly đầy đủ' : '1/2 Kelly';
      el('k-result').innerHTML = `
        <div class="flex-between">
          <span class="muted small">Phân bổ theo ${modeLabel}</span>
          <span class="big pos">${r.used_fraction_pct}% vốn</span>
        </div>
        <div class="kv-list mt-8">
          <div class="kv-row"><span class="k">Kelly đầy đủ / 1/2 Kelly</span><span class="v">${r.kelly_full_pct}% / ${r.kelly_half_pct}%</span></div>
          <div class="kv-row"><span class="k">Số tiền giải ngân (tối đa)</span><span class="v">${fmt.money(r.amount)}</span></div>
          <div class="kv-row"><span class="k">Khối lượng đề xuất</span><span class="v">${fmt.num(r.quantity)} CP</span></div>
          <div class="kv-row"><span class="k">Rủi ro nếu chạm cắt lỗ</span><span class="v neg">${fmt.money(r.risk_amount)}</span></div>
          <div class="kv-row"><span class="k">Giới hạn theo tỷ trọng tối đa</span><span class="v">${fmt.money(r.cap_amount)}</span></div>
        </div>
        <ul class="kelly-notes">${(r.notes || []).map((n) => `<li>${fmt.escape(n)}</li>`).join('')}</ul>`;
      el('k-result').classList.remove('hidden');
    } catch (err) {
      toast(err.message, 'error', 'Kelly 1/2');
    }
  }

  function renderFib(p) {
    const fib = p.fib || {};
    const dir = fib.direction === 'UP' ? 'Xu hướng TĂNG' : fib.direction === 'DOWN' ? 'Xu hướng GIẢM' : '—';
    const dirEl = el('fib-direction');
    dirEl.textContent = dir;
    dirEl.className = 'chip ' + (fib.direction === 'UP' ? 'pos' : fib.direction === 'DOWN' ? 'neg' : '');
    el('fib-kv').innerHTML = [
      ['Đỉnh swing', fib.anchor_high ? `${fmt.price(fib.anchor_high.price)} đ (${fib.anchor_high.date})` : '—'],
      ['Đáy swing', fib.anchor_low ? `${fmt.price(fib.anchor_low.price)} đ (${fib.anchor_low.date})` : '—'],
      ['Vùng vàng 0.5–0.618', fib.golden_zone && fib.golden_zone.length ? `${fmt.price(fib.golden_zone[0])} – ${fmt.price(fib.golden_zone[1])} đ` : '—'],
      ['Mức thoái lui hiện tại', fib.retracement_pct != null ? fib.retracement_pct + '%' : '—'],
    ].map(([k, v]) => `<div class="kv-row"><span class="k">${k}</span><span class="v">${v}</span></div>`).join('');

    const rows = [];
    rows.push('<tr><th>Mức</th><th class="num">Giá</th><th class="num">Cách giá</th></tr>');
    (fib.levels || []).forEach((l) => {
      const golden = l.ratio === 0.5 || l.ratio === 0.618;
      const diff = p.price ? ((l.price - p.price) / p.price * 100) : null;
      rows.push(`<tr class="${golden ? 'hl-fib' : ''}">
        <td>${FIB_LABELS[l.ratio] || ('Fib ' + l.ratio)}</td>
        <td class="num">${fmt.price(l.price)}</td>
        <td class="num ${fmt.tone(diff)}">${fmt.pct(diff)}</td></tr>`);
    });
    (fib.extensions || []).forEach((l) => {
      const diff = p.price ? ((l.price - p.price) / p.price * 100) : null;
      rows.push(`<tr><td>Mở rộng ${l.ratio}</td><td class="num">${fmt.price(l.price)}</td>
        <td class="num ${fmt.tone(diff)}">${fmt.pct(diff)}</td></tr>`);
    });
    el('fib-table').innerHTML = rows.join('');
    el('fib-note').textContent = fib.in_golden_zone
      ? '✅ Giá đang nằm trong vùng vàng Fibonacci 0.5–0.618 — vùng mua ưu tiên trong xu hướng tăng.'
      : (fib.direction === 'DOWN'
        ? '⚠️ Cấu trúc Fibonacci đang giảm — các mức Fib là kháng cự, ưu tiên đứng ngoài chờ tạo đáy.'
        : 'Mua ưu tiên khi giá điều chỉnh về vùng vàng 0.5–0.618.');
  }

  function renderPivot(p) {
    const piv = p.pivots || {};
    const cols = [['daily', 'Phiên'], ['weekly', 'Tuần'], ['monthly', 'Tháng']];
    const rows = ['r3', 'r2', 'r1', 'p', 's1', 's2', 's3'];
    const names = { r3: 'R3', r2: 'R2', r1: 'R1', p: 'Pivot', s1: 'S1', s2: 'S2', s3: 'S3' };
    let html = '<tr><th>Mức</th>' + cols.map(([, label]) => `<th class="num">${label}</th>`).join('') + '</tr>';
    rows.forEach((key) => {
      html += `<tr class="${key === 'p' ? 'hl-fib' : ''}"><td>${names[key]}</td>`;
      cols.forEach(([colKey]) => {
        const value = (piv[colKey] || {})[key];
        html += `<td class="num">${value != null ? fmt.price(value) : '—'}</td>`;
      });
      html += '</tr>';
    });
    el('pivot-table').innerHTML = html;
  }

  function srList(items) {
    if (!items || !items.length) return '<p class="small muted">Chưa phát hiện mức đáng tin cậy</p>';
    return items.map((s) => `
      <div class="level-item">
        <span class="lbl">${fmt.price(s.price)} đ · ${s.touches} lần chạm</span>
        <span class="prc ${fmt.tone(s.distance_pct)}">${fmt.pct(s.distance_pct)}</span>
      </div>`).join('');
  }

  function renderSupportsResistances(p) {
    el('sr-supports').innerHTML = srList(p.supports);
    el('sr-resistances').innerHTML = srList(p.resistances);
  }

  function renderIndicators(p) {
    const ind = p.indicators || {};
    const r = [];
    const add = (k, v, cls = '') => r.push(`<div class="kv-row"><span class="k">${k}</span><span class="v ${cls}">${v}</span></div>`);
    add('RSI (14)', ind.rsi != null ? ind.rsi : '—', ind.rsi > 70 ? 'neg' : ind.rsi < 30 ? 'pos' : '');
    add('MACD histogram', ind.macd_hist != null ? ind.macd_hist : '—', fmt.tone(ind.macd_hist));
    add('ATR (14)', ind.atr != null ? fmt.num(ind.atr, 0) + ' đ' : '—');
    add('KL so với TB20', ind.volume_ratio != null ? ind.volume_ratio + '×' : '—');
    add('SMA 20', ind.ma20 != null ? fmt.price(ind.ma20) + ' đ' : '—', p.price > ind.ma20 ? 'pos' : 'neg');
    add('SMA 50', ind.ma50 != null ? fmt.price(ind.ma50) + ' đ' : '—', ind.ma50 && p.price > ind.ma50 ? 'pos' : 'neg');
    add('SMA 200', ind.ma200 != null ? fmt.price(ind.ma200) + ' đ' : '—', ind.ma200 && p.price > ind.ma200 ? 'pos' : 'neg');
    add('Bollinger (20,2)', ind.bb_lower != null ? `${fmt.price(ind.bb_lower)} – ${fmt.price(ind.bb_upper)} đ` : '—');
    el('indicators-kv').innerHTML = r.join('');
  }

  function renderBacktest(p) {
    const bt = p.backtest;
    el('backtest-source').textContent = p.score_history ? `${(p.score_history || []).length} phiên mô phỏng` : '—';
    if (!bt || !bt.trades) {
      el('backtest-kv').innerHTML = '<p class="small muted">Chưa đủ tín hiệu lịch sử để kiểm định trên mã này. Kelly sẽ dùng xác suất ước lượng từ điểm tín hiệu hiện tại.</p>';
      return;
    }
    const r = [];
    const add = (k, v, cls = '') => r.push(`<div class="kv-row"><span class="k">${k}</span><span class="v ${cls}">${v}</span></div>`);
    add('Số lệnh mô phỏng', bt.trades);
    add('Tỷ lệ thắng', bt.win_rate + '%', bt.win_rate >= 50 ? 'pos' : 'neg');
    add('Lãi TB / Lỗ TB', `${bt.avg_win_pct}% / ${bt.avg_loss_pct}%`);
    add('Payoff (lãi/lỗ)', bt.payoff != null ? bt.payoff : '—');
    add('Kỳ vọng mỗi lệnh', bt.expectancy_pct + '%', fmt.tone(bt.expectancy_pct));
    add('Max drawdown', bt.max_drawdown_pct + '%', 'neg');
    if (bt.profit_factor != null) add('Profit factor', bt.profit_factor);
    el('backtest-kv').innerHTML = r.join('');
  }

  function renderDividends(p) {
    const f = p.fundamentals;
    const r = [];
    const add = (k, v, cls = '') => r.push(`<div class="kv-row"><span class="k">${k}</span><span class="v ${cls}">${v}</span></div>`);
    if (!f) {
      el('dividend-kv').innerHTML = '<p class="small muted">Chưa lấy được dữ liệu cơ bản cho mã này.</p>';
      el('dividend-table').classList.add('hidden');
      return;
    }
    add('Cổ tức tiền mặt 12 tháng', f.dividend_ttm ? fmt.num(f.dividend_ttm) + ' đ/CP' : '—');
    add('Tỷ suất cổ tức', f.dividend_yield != null ? f.dividend_yield + '%' : '—', 'pos');
    if (f.market_cap) add('Vốn hóa', fmt.money(f.market_cap) + ' đ');
    if (f.rating) add('Khuyến nghị (Vietcap IQ)', f.rating);
    if (f.target_price) add('Giá mục tiêu', fmt.price(f.target_price) + ' đ');
    if (f.sector) add('Ngành', f.sector);
    el('dividend-kv').innerHTML = r.join('');
    const events = f.dividend_events || [];
    const table = el('dividend-table');
    if (events.length) {
      table.innerHTML = '<tr><th>Ngày GDKHQ</th><th class="num">Tiền mặt</th><th>Nội dung</th></tr>' +
        events.slice(0, 6).map((e) => `<tr><td>${fmt.escape(e.ex_date)}</td>
          <td class="num">${fmt.num(e.amount)} đ</td>
          <td class="small muted">${fmt.escape(e.title || '')}</td></tr>`).join('');
      table.classList.remove('hidden');
    } else {
      table.classList.add('hidden');
    }
  }

  /* ------------------------------------------- advanced (member-only) module */

  const PATTERN_TONE = { 'Mua': 'tone-up', 'Bán': 'tone-down' };

  function patternCard(pattern) {
    const hit = ['Mua', 'Bán', 'Theo dõi'].includes(pattern.signal);
    const badge = `<span class="badge ${PATTERN_TONE[pattern.signal] || 'tone-neutral'}">${fmt.escape(pattern.signal)}</span>`;
    const message = pattern.message
      ? `<div class="pattern-msg">${fmt.escape(pattern.message)}</div>` : '';
    const details = [
      pattern.neckline ? `Cổ: ${fmt.price(pattern.neckline)}` : '',
      pattern.support ? `Đáy: ${fmt.price(pattern.support)}` : '',
      pattern.volume_ratio ? `KL: ${pattern.volume_ratio}×` : '',
    ].filter(Boolean).join(' · ');
    return `<div class="pattern-item ${hit ? 'hit' : 'miss'}">
      <div class="pattern-top"><strong>${fmt.escape(pattern.name)}</strong>${badge}</div>
      ${details ? `<div class="pattern-msg tnum">${fmt.escape(details)}</div>` : ''}
      ${message}
    </div>`;
  }

  function renderAdvanced(adv) {
    el('adv-updated').textContent = `Cập nhật: ${adv.updated_at || ''} · ${(adv.sessions || 0)} phiên`;
    const biasEl = el('adv-bias');
    biasEl.textContent = adv.bias_label || '—';
    biasEl.className = 'chip ' + (adv.bias === 'Bullish' ? 'pos' : adv.bias === 'Bearish' ? 'neg' : '');
    const trend = adv.trend || {};
    const trendTone = trend.signal === 'Bullish' ? 'pos' : trend.signal === 'Bearish' ? 'neg' : '';
    el('adv-trend').innerHTML = `Xu hướng: <span class="${trendTone}">${fmt.escape(trend.signal || '—')} (${trend.momentum != null ? (trend.momentum > 0 ? '+' : '') + trend.momentum + '%' : '—'})</span>`;
    el('adv-summary').textContent = adv.summary || '';

    const swing = adv.swing || {};
    const swingRow = (p) => `<div class="swing-item"><span>${fmt.price(p.price)} đ</span><span class="muted">${fmt.escape(p.date || '')}</span></div>`;
    el('adv-peaks').innerHTML = (swing.peaks || []).map(swingRow).join('') || '<p class="small muted">Chưa xác định</p>';
    el('adv-troughs').innerHTML = (swing.troughs || []).map(swingRow).join('') || '<p class="small muted">Chưa xác định</p>';
    el('adv-structure').textContent = swing.structure || '';

    const candles = adv.candle_patterns || [];
    el('adv-candle-count').textContent = `${candles.filter((c) => ['Mua', 'Bán', 'Theo dõi'].includes(c.signal)).length}/${candles.length} mẫu`;
    el('adv-candles').innerHTML = candles.map(patternCard).join('') || '<p class="small muted">Không có dữ liệu nến</p>';

    const charts = adv.chart_patterns || [];
    el('adv-chart-count').textContent = `${charts.filter((c) => ['Mua', 'Bán', 'Theo dõi'].includes(c.signal)).length}/${charts.length} mẫu`;
    el('adv-chart-patterns').innerHTML = charts.map(patternCard).join('') || '<p class="small muted">Không có dữ liệu mô hình</p>';
  }

  async function loadAdvanced(symbol, refresh) {
    const section = el('advanced-section');
    const lockBox = el('advanced-locked');
    if (!section || !lockBox) return;
    if (!loadAdvanced.lockHtml) loadAdvanced.lockHtml = lockBox.innerHTML;
    section.classList.remove('hidden');
    lockBox.innerHTML = loadAdvanced.lockHtml;
    try {
      const adv = await fetchJSON(`/api/analysis/advanced?symbol=${encodeURIComponent(symbol)}${refresh ? '&refresh=1' : ''}`);
      lockBox.classList.add('hidden');
      el('advanced-view').classList.remove('hidden');
      renderAdvanced(adv);
    } catch (err) {
      lockBox.classList.remove('hidden');
      el('advanced-view').classList.add('hidden');
      const msg = (err && err.message) || 'Không tải được phân tích chuyên sâu.';
      if (!msg.includes('đăng nhập')) {
        lockBox.innerHTML = `<strong>🔒 Phân tích chuyên sâu</strong>${fmt.escape(msg)}
          <div class="flex mt-12" style="gap:8px;justify-content:center;">
            <a class="btn btn-primary" href="/dang-nhap">Đăng nhập</a>
            <a class="btn btn-ghost" href="/dang-ky">Đăng ký bằng email</a>
          </div>`;
      }
    }
  }

  /* ------------------------------------------------------------------ init */

  document.addEventListener('DOMContentLoaded', () => {
    const params = new URLSearchParams(window.location.search);
    const initial = params.get('symbol');
    el('analyze-form').addEventListener('submit', (ev) => {
      ev.preventDefault();
      analyze(el('symbol-input').value, false);
    });
    el('refresh-btn').addEventListener('click', () => {
      const sym = el('symbol-input').value || (current && current.symbol);
      if (sym) analyze(sym, true);
    });
    el('k-calc').addEventListener('click', calcKelly);
    el('watch-btn').addEventListener('click', async () => {
      if (!current) return;
      try {
        await postJSON('/api/portfolio/watch', { symbol: current.symbol });
        toast(`Đã thêm ${current.symbol} vào danh mục theo dõi và sẽ cảnh báo khi có tín hiệu mua/bán.`, 'success', 'Theo dõi');
      } catch (err) {
        toast(err.message, 'error', 'Theo dõi');
      }
    });
    if (initial) analyze(initial, false);
  });
})();
