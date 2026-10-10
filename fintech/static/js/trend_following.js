(function () {
  'use strict';
  const { fmt, fetchJSON, postJSON, toast, showState } = App;
  const el = (id) => document.getElementById(id);
  let currentSymbol = null;

  function renderTrendFollowing(tf) {
    const sec = el('trend-following-section');
    if (!sec) return;
    if (!tf) {
      sec.classList.add('hidden');
      return;
    }
    sec.classList.remove('hidden');

    const kelly = tf.step3_kelly || {};
    const f = (tf.step1_filter && tf.step1_filter.fundamental) || {};
    if (el('tf-nav-input') && !el('tf-nav-input').dataset.dirty) {
      el('tf-nav-input').value = kelly.nav || 500000000;
    }
    if (el('tf-eps-input') && !el('tf-eps-input').dataset.dirty) {
      el('tf-eps-input').value = f.eps_growth_pct != null ? f.eps_growth_pct : 18;
    }
    if (el('tf-macro-checkbox') && !el('tf-macro-checkbox').dataset.dirty) {
      el('tf-macro-checkbox').checked = f.is_macro_favored !== false;
    }

    const entry = tf.step2_entry || {};
    const filter = tf.step1_filter || {};
    let statusHtml = '';
    if (entry.status === 'MUA_THAM_DO') {
      statusHtml = '<span class="tf-badge pass">KÍCH HOẠT MUA ĐỢT 1</span>';
    } else if (entry.status === 'MUA_GIA_TANG') {
      statusHtml = '<span class="tf-badge pass">KÍCH HOẠT MUA ĐỢT 2</span>';
    } else if (filter.passed) {
      statusHtml = '<span class="tf-badge info">ĐẠT BỘ LỌC XU HƯỚNG</span>';
    } else {
      statusHtml = '<span class="tf-badge fail">CHƯA ĐẠT BỘ LỌC</span>';
    }
    el('tf-status-badge').innerHTML = statusHtml;

    // Bước 1: Bộ lọc Xu hướng & Cơ bản
    const s1Badge = el('tf-step1-badge');
    s1Badge.className = 'tf-badge ' + (filter.passed ? 'pass' : 'fail');
    s1Badge.textContent = filter.passed ? 'ĐẠT BỘ LỌC' : 'CHƯA ĐẠT';

    const trend = filter.trend || {};
    el('tf-step1-kv').innerHTML = [
      ['Ngành vĩ mô', `${fmt.escape(f.sector || '—')} ${f.is_macro_favored ? '<span class="pos">✓ Hưởng lợi</span>' : '<span class="muted">· Trung tính</span>'}`],
      ['Tăng trưởng EPS', `${f.eps_growth_pct != null ? (f.eps_growth_pct > 0 ? '+' : '') + f.eps_growth_pct + '%' : '—'} ${f.eps_passed ? '<span class="pos">✓ Đạt &gt;15%</span>' : '<span class="neg">✗ Chưa đạt</span>'}`],
      ['Thanh khoản V20', `${fmt.vol(f.v20)} cp/phiên ${f.v20_passed ? '<span class="pos">✓ Đạt &ge;500k</span>' : '<span class="neg">✗ Dưới 500k</span>'}`],
      ['Xu hướng dài hạn', `Giá: ${fmt.price(trend.price)} | EMA200: ${fmt.price(trend.ema200)} ${trend.price_above_ema200 ? '<span class="pos">✓ Giá &gt; EMA200</span>' : '<span class="neg">✗ Giá &lt; EMA200</span>'}`],
      ['Xu hướng trung hạn', `EMA50: ${fmt.price(trend.ema50)} ${trend.golden_cross ? '<span class="pos">✓ Golden Cross (EMA50 &gt; EMA200)</span>' : '<span class="neg">✗ EMA50 &lt; EMA200</span>'}`],
    ].map(([k, v]) => `<div class="kv-row"><span class="k">${k}</span><span class="v">${v}</span></div>`).join('');

    el('tf-step1-note').textContent = filter.passed
      ? 'Đủ điều kiện xu hướng tăng & yếu tố cơ bản theo tiêu chuẩn Ed Thorp.'
      : 'Chưa đủ điều kiện xu hướng tăng hoặc yếu tố cơ bản. Ưu tiên quan sát chờ tích lũy.';

    // Bước 2: Điểm mua (Entry Trigger)
    const s2Badge = el('tf-step2-badge');
    let s2Class = 'warn';
    if (['MUA_THAM_DO', 'MUA_GIA_TANG'].includes(entry.status)) s2Class = 'pass';
    else if (entry.status === 'KHONG_DAT_LOC') s2Class = 'fail';
    s2Badge.className = 'tf-badge ' + s2Class;
    s2Badge.textContent = entry.label || entry.status;

    el('tf-step2-kv').innerHTML = [
      ['Hỗ trợ EMA 50', `${fmt.price(trend.ema50)} đ ${entry.near_ema50 ? '<span class="pos">● Đang test</span>' : ''}`],
      ['Hỗ trợ Mid-BB (MA20)', `${fmt.price(trend.mid_bb_ma20)} đ ${entry.near_mid_bb ? '<span class="pos">● Đang test</span>' : ''}`],
      ['Nến đảo chiều', `${fmt.escape(entry.reversal_name || '—')} ${entry.has_reversal_candle ? '<span class="pos">✓</span>' : ''}`],
      ['Khối lượng retest', `${entry.volume_ratio != null ? entry.volume_ratio + '× V20' : '—'} ${entry.is_low_volume ? '<span class="pos">✓ Kiệt vol (&le;1.05x)</span>' : '<span class="muted">Vol cao</span>'}`],
      ['Đỉnh ngắn hạn xác nhận', `${fmt.price(entry.recent_swing_high)} đ ${entry.breakout_confirmed ? '<span class="pos">✓ Breakout vol lớn</span>' : ''}`],
    ].map(([k, v]) => `<div class="kv-row"><span class="k">${k}</span><span class="v">${v}</span></div>`).join('');

    el('tf-step2-reasons').innerHTML = (entry.reasons || []).map((r) => `<li>${fmt.escape(r)}</li>`).join('')
      || '<li>Chờ nhịp điều chỉnh kiểm định hỗ trợ hoặc breakout xác nhận.</li>';

    // Bước 3: Định cỡ vị thế 1/10 Kelly
    el('tf-step3-kv').innerHTML = [
      ['Tỷ lệ thắng (W) / Payoff (R)', `${kelly.win_rate_pct}% / ${kelly.payoff}:1`],
      ['Kelly chuẩn (K)', `${kelly.standard_kelly_pct}% NAV`],
      ['1/10 Kelly (Ed Thorp)', `<b class="pos">${kelly.fractional_kelly_pct}% NAV</b> (lý thuyết cực hạn)`],
      ['Phân bổ thực tế tại VN', `<b class="pos">${kelly.cap_pct}% NAV</b> (tối đa 10-15%/mã)`],
      ['Tổng ngân sách giải ngân', `<b>${fmt.price(kelly.total_amount)} đ</b>`],
      ['Khối lượng CP đề xuất', `<b class="pos">${fmt.num(kelly.total_qty)} CP</b> (làm tròn lô 100)`],
    ].map(([k, v]) => `<div class="kv-row"><span class="k">${k}</span><span class="v">${v}</span></div>`).join('');

    el('tf-step3-notes').innerHTML = (kelly.notes || []).map((n) => `<li>${fmt.escape(n)}</li>`).join('');

    // Bước 4: Điểm cắt lỗ & Quản trị T+2.5
    const risk = tf.step4_risk_t_plus || {};
    el('tf-step4-kv').innerHTML = [
      ['Cắt lỗ cứng (-7%)', `<span class="neg">${fmt.price(risk.hard_stop_loss_price)} đ</span> (-7.0%)`],
      ['Cắt lỗ thủng EMA 50', `<span class="neg">${fmt.price(risk.ema50_stop_price)} đ</span>`],
      ['Mức cắt lỗ khuyến nghị', `<b class="neg">${fmt.price(risk.stop_loss_price)} đ</b>`],
      ['Rủi ro tối đa (tổng vị thế)', `<span class="neg">${fmt.price(risk.max_risk_amount)} đ</span>`],
    ].map(([k, v]) => `<div class="kv-row"><span class="k">${k}</span><span class="v">${v}</span></div>`).join('');

    const t1 = risk.tranche1 || {};
    const t2 = risk.tranche2 || {};
    el('tf-tranches-wrap').innerHTML = `
      <div class="tf-tranche-card">
        <strong>${fmt.escape(t1.label || 'Đợt 1')}</strong>
        <div>KL: <b>${fmt.num(t1.quantity)} CP</b> (50%)</div>
        <div>Vốn: ${fmt.price(t1.amount)} đ</div>
        <p class="small muted mt-4">${fmt.escape(t1.entry_desc || '')}</p>
      </div>
      <div class="tf-tranche-card">
        <strong>${fmt.escape(t2.label || 'Đợt 2')}</strong>
        <div>KL: <b>${fmt.num(t2.quantity)} CP</b> (50%)</div>
        <div>Vốn: ${fmt.price(t2.amount)} đ</div>
        <p class="small muted mt-4">${fmt.escape(t2.entry_desc || '')}</p>
      </div>
    `;
    el('tf-step4-defense').innerHTML = `🛡️ <b>Phòng vệ T+2.5:</b> ${fmt.escape(risk.defense_rule || '')}`;

    // Bước 5: Trailing Stop
    const s5 = tf.step5_trailing_stop || {};
    const s5Badge = el('tf-step5-badge');
    const s5Class = s5.tone === 'up' ? 'pass' : (s5.tone === 'down' ? 'fail' : 'warn');
    s5Badge.className = 'tf-badge ' + s5Class;
    s5Badge.textContent = s5.holding_status || '—';

    el('tf-step5-kv').innerHTML = [
      ['Trailing Stop (EMA 20)', `<b class="pos">${fmt.price(s5.trailing_stop_ema20)} đ</b> (ngưỡng giữ)`],
      ['Bán dứt khoát (EMA 50)', `<b class="neg">${fmt.price(s5.exit_trigger_ema50)} đ</b> (ngưỡng thoát 100%)`],
      ['Giá thị trường hiện tại', `${fmt.price(trend.price)} đ`],
    ].map(([k, v]) => `<div class="kv-row"><span class="k">${k}</span><span class="v">${v}</span></div>`).join('');

    el('tf-step5-advice').textContent = s5.advice || '';
    el('tf-step5-rules').innerHTML = `
      <div>• <b>Quy tắc giữ:</b> ${fmt.escape(s5.rule_hold || '')}</div>
      <div class="mt-4">• <b>Quy tắc bán:</b> ${fmt.escape(s5.rule_exit || '')}</div>
    `;

    // Summary table
    const rows = tf.summary_table || [];
    el('tf-summary-tbody').innerHTML = rows.map((r) => `
      <tr>
        <td><strong>${fmt.escape(r.component)}</strong></td>
        <td>${fmt.escape(r.detail)}</td>
        <td class="tnum">${fmt.escape(r.value || '—')}</td>
        <td style="text-align:center;">
          ${r.passed ? '<span class="tf-badge pass">ĐẠT</span>' : '<span class="tf-badge fail">CHƯA ĐẠT</span>'}
        </td>
      </tr>
    `).join('');
  }
  async function recalcTrendFollowing() {
    if (!current) return;
    const navVal = parseFloat(el('tf-nav-input').value) || 500000000;
    const epsVal = parseFloat(el('tf-eps-input').value);
    const macroVal = el('tf-macro-checkbox').checked;
    el('tf-nav-input').dataset.dirty = '1';
    el('tf-eps-input').dataset.dirty = '1';
    el('tf-macro-checkbox').dataset.dirty = '1';
    const btn = el('tf-recalc-btn');
    btn.disabled = true;
    try {
      const updated = await postJSON('/api/trend-following/calc', {
        symbol: currentSymbol,
        equity: navVal,
        eps_growth: isNaN(epsVal) ? null : epsVal,
        macro_confirmed: macroVal,
      });
      
      renderTrendFollowing(updated);
      toast('Đã cập nhật tính toán chiến lược Trend Following', 'success', 'Trend Following');
    } catch (err) {
      toast(err.message, 'error', 'Trend Following');
    } finally {
      btn.disabled = false;
    }
  }

  async function analyze(symbol) {
    if (!symbol) return;
    symbol = symbol.toUpperCase();
    currentSymbol = symbol;
    window.history.replaceState(null, '', '?symbol=' + encodeURIComponent(symbol));
    
    try {
        const data = await fetchJSON('/api/analyze?symbol=' + encodeURIComponent(symbol));
        if (data && data.trend_following) {
            renderTrendFollowing(data.trend_following);
            el('trend-following-section').classList.remove('hidden');
        } else {
            toast("Không có dữ liệu trend following", "error");
        }
    } catch (err) {
        toast(err.message, "error");
    }
    
  }


  async function runBacktest(strategy) {
    if (!currentSymbol) return;
    const btn = el('bt-btn');
    btn.disabled = true;
    btn.textContent = 'Đang chạy...';
    try {
      const payload = {
        symbol: currentSymbol,
        start_date: el('bt-start').value,
        end_date: el('bt-end').value
      };
      const res = await postJSON('/api/backtest/' + strategy, payload);
      
      const sum = res.summary || {};
      el('bt-total').textContent = sum.total || 0;
      el('bt-winrate').textContent = (sum.win_rate_pct || 0) + '%';
      
      const isDeriv = strategy === 'derivatives';
      const unit = isDeriv ? ' điểm' : '%';
      
      el('bt-return').textContent = (sum.total_return || 0) + unit;
      el('bt-return').className = 'value tnum ' + (sum.total_return > 0 ? 'pos' : (sum.total_return < 0 ? 'neg' : ''));
      el('bt-maxloss').textContent = (sum.max_loss || 0) + unit;
      
      const tbody = document.querySelector('#bt-table tbody');
      const trades = res.trades || [];
      if (!trades.length) {
        tbody.innerHTML = '<tr><td colspan="7" class="muted text-center">Không có giao dịch nào trong khoảng thời gian này.</td></tr>';
      } else {
        // Reverse to show latest first
        tbody.innerHTML = trades.reverse().slice(0, 50).map(t => {
            const pnl = t.pnl !== undefined ? t.pnl : t.pnl_pct;
            const type = t.type || 'LONG';
            return `<tr>
              <td>${t.entry_date}</td>
              <td>${type === 'LONG' ? '<span class="pos">LONG</span>' : '<span class="neg">SHORT</span>'}</td>
              <td class="num">${t.entry_price}</td>
              <td>${t.exit_date}</td>
              <td class="num">${t.exit_price}</td>
              <td class="num ${pnl > 0 ? 'pos' : 'neg'}">${pnl}${unit}</td>
              <td>${t.reason}</td>
            </tr>`;
        }).join('');
      }
      
      el('bt-result').classList.remove('hidden');
    } catch (err) {
      toast(err.message, 'error');
    } finally {
      btn.disabled = false;
      btn.textContent = 'Chạy Backtest';
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    const params = new URLSearchParams(window.location.search);
    const initial = params.get('symbol');
    
    el('tool-form').addEventListener('submit', (ev) => {
      ev.preventDefault();
      analyze(el('tool-symbol').value);
    });
    
    if (el('tf-recalc-btn')) el('tf-recalc-btn').addEventListener('click', recalcTrendFollowing);

        if (el('bt-end')) el('bt-end').value = '2026-10-10';
    el('bt-form').addEventListener('submit', (ev) => { ev.preventDefault(); runBacktest('trend_following'); });

    if (initial) {
      el('tool-symbol').value = initial;
      analyze(initial);
    }
  });
})();
