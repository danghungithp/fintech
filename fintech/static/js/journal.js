/* FinViet Pro — trading journal (sổ giao dịch) */
(function () {
  'use strict';
  const { fmt, fetchJSON, postJSON, toast } = App;

  const el = (id) => document.getElementById(id);

  function sideBadge(side, label) {
    const tone = side === 'BUY' ? 'tone-up' : 'tone-down';
    return `<span class="badge ${tone}">${fmt.escape(label || side)}</span>`;
  }

  function renderSummary(s) {
    const cards = [
      { label: 'Tổng lệnh', value: `${fmt.num(s.trades_count)} <small class="muted">(${fmt.num(s.buy_count)} mua / ${fmt.num(s.sell_count)} bán)</small>` },
      { label: 'Lãi/lỗ thực hiện', value: `<span class="${fmt.tone(s.realized_pnl)}">${s.realized_pnl > 0 ? '+' : ''}${fmt.money(s.realized_pnl)}</span>`, tone: fmt.tone(s.realized_pnl) },
      {
        label: 'Tỷ lệ thắng',
        value: s.win_rate != null
          ? `${s.win_rate}% <small class="muted">(${s.win_trades} thắng / ${s.loss_trades} lỗ)</small>`
          : '<small class="muted">Chưa có lệnh bán khớp</small>',
        tone: s.win_rate != null ? (s.win_rate >= 50 ? 'pos' : 'neg') : '',
      },
      { label: 'Vốn đang nắm giữ', value: fmt.money(s.open_cost), note: `${(s.open_positions || []).length} mã` },
    ];
    el('journal-summary').innerHTML = cards.map((c) => `
      <div class="card stat-card">
        <p class="small muted">${c.label}</p>
        <p class="big tnum ${c.tone || ''}">${c.value}</p>
        ${c.note ? `<p class="small muted">${c.note}</p>` : ''}
      </div>`).join('');
  }

  function renderTrades(trades, realizedById) {
    el('journal-count').textContent = `${trades.length} lệnh`;
    const rows = ['<tr><th>Ngày</th><th>Mã</th><th>Hướng</th><th class="num">Khối lượng</th><th class="num">Giá</th><th class="num">Giá trị</th><th class="num">Phí</th><th class="num">Lãi/lỗ thực hiện</th><th>Ghi chú</th><th></th></tr>'];
    trades.forEach((t) => {
      const pnl = realizedById ? realizedById[t.id] : null;
      rows.push(`<tr>
        <td class="tnum">${fmt.escape(t.trade_date)}</td>
        <td><b>${fmt.escape(t.symbol)}</b></td>
        <td>${sideBadge(t.side, t.side_label)}</td>
        <td class="num">${fmt.num(t.quantity)}</td>
        <td class="num">${fmt.num(t.price, 2)}</td>
        <td class="num">${fmt.money(t.value)}</td>
        <td class="num muted">${t.fee ? fmt.money(t.fee) : '—'}</td>
        <td class="num ${pnl != null ? fmt.tone(pnl) : ''}">${pnl != null ? (pnl > 0 ? '+' : '') + fmt.money(pnl) : '<span class="muted">—</span>'}</td>
        <td class="small muted">${fmt.escape(t.note || '')}</td>
        <td><button class="btn btn-xs btn-ghost trade-del" data-id="${t.id}" title="Xóa lệnh">✕</button></td>
      </tr>`);
    });
    el('journal-table').innerHTML = rows.join('');
    el('journal-table').querySelectorAll('.trade-del').forEach((btn) => {
      btn.addEventListener('click', async () => {
        if (!window.confirm('Xóa lệnh giao dịch này?')) return;
        try {
          await postJSON(`/api/trades/${btn.dataset.id}`, {}, 'DELETE');
          toast('Đã xóa lệnh.', 'success', 'Sổ giao dịch');
          loadAll();
        } catch (err) {
          toast(err.message, 'error', 'Xóa lệnh thất bại');
        }
      });
    });
  }

  function renderPositions(positions) {
    const rows = ['<tr><th>Mã</th><th class="num">Khối lượng</th><th class="num">Giá vốn TB</th><th class="num">Vốn</th></tr>'];
    (positions || []).forEach((p) => {
      rows.push(`<tr>
        <td><b>${fmt.escape(p.symbol)}</b></td>
        <td class="num">${fmt.num(p.quantity)}</td>
        <td class="num">${fmt.num(p.avg_cost, 2)}</td>
        <td class="num">${fmt.money(p.cost)}</td>
      </tr>`);
    });
    el('positions-table').innerHTML = rows.join('') +
      ((positions || []).length ? '' : '<tr><td colspan="4" class="small muted" style="text-align:center;padding:16px;">Không có vị thế nào (đã bán hết hoặc chưa có lệnh mua)</td></tr>');
  }

  async function loadAll() {
    const data = await fetchJSON('/api/trades');
    renderSummary(data.summary || {});
    renderTrades(data.trades || [], (data.summary || {}).realized_by_id);
    renderPositions((data.summary || {}).open_positions);
  }

  async function submitTrade(ev) {
    ev.preventDefault();
    const body = {
      trade_date: el('t-date').value,
      symbol: el('t-symbol').value.trim().toUpperCase(),
      side: el('t-side').value,
      quantity: parseFloat(el('t-qty').value),
      price: parseFloat(el('t-price').value),
      fee: parseFloat(el('t-fee').value) || 0,
      note: el('t-note').value.trim(),
    };
    try {
      await postJSON('/api/trades', body);
      toast(`Đã thêm lệnh ${body.side === 'BUY' ? 'MUA' : 'BÁN'} ${body.symbol}.`, 'success', 'Sổ giao dịch');
      el('t-note').value = '';
      loadAll();
    } catch (err) {
      toast(err.message, 'error', 'Thêm lệnh thất bại');
    }
  }

  document.addEventListener('DOMContentLoaded', async () => {
    let user = null;
    try {
      const me = await fetchJSON('/api/auth/me');
      user = me && me.user;
    } catch (e) { /* logged out */ }
    if (!user) return; // keep the lock card visible

    el('journal-locked').classList.add('hidden');
    el('journal-app').classList.remove('hidden');

    el('t-date').value = new Date().toISOString().slice(0, 10);
    el('trade-form').addEventListener('submit', submitTrade);

    try {
      const data = await fetchJSON('/api/symbols?limit=100');
      el('trade-symbol-suggest').innerHTML = (data.symbols || [])
        .map((s) => `<option value="${fmt.escape(s.symbol)}">`).join('');
    } catch (e) { /* suggestions optional */ }

    try {
      await loadAll();
    } catch (err) {
      toast(err.message, 'error', 'Không tải được sổ giao dịch');
    }
  });
})();
