/* FinViet Pro — portfolio page */
(function () {
  'use strict';
  const { fmt, fetchJSON, postJSON, toast, signalBadge, modal, closeModal } = App;
  const el = (id) => document.getElementById(id);

  const PALETTE = ['#38bdf8', '#6366f1', '#16c784', '#f5a524', '#ec4899', '#22d3ee', '#a78bfa', '#f97316', '#84cc16', '#e879f9'];
  let overview = { positions: [], watchlist: [], summary: {} };
  let symbolCache = null;

  /* ------------------------------------------------------------- loading */

  async function loadOverview() {
    try {
      const data = await fetchJSON('/api/portfolio/overview');
      overview = data;
      renderSummary(data.summary || {});
      renderPositions(data.positions || []);
      renderWatchlist(data.watchlist || []);
      renderAllocation(data.positions || [], data.summary || {});
      el('pf-alerts').textContent = data.alerts_count || 0;
      el('pf-alerts').className = 'value tnum ' + (data.alerts_count ? 'neg' : 'pos');
    } catch (err) {
      toast(err.message, 'error', 'Không tải được danh mục');
    }
  }

  function renderSummary(s) {
    el('pf-value').textContent = s.positions ? fmt.money(s.market_value) : '0 đ';
    const pnlEl = el('pf-pnl');
    if (s.positions) {
      pnlEl.innerHTML = `${fmt.money(s.pnl)} (${fmt.pct(s.pnl_pct)}) · ${s.positions} vị thế`;
      pnlEl.className = 'delta tnum ' + fmt.tone(s.pnl);
    } else {
      pnlEl.textContent = 'Chưa có vị thế nào';
      pnlEl.className = 'delta tnum muted';
    }
    el('pf-cost').textContent = fmt.money(s.equity);
    el('pf-cash').textContent = `Đã giải ngân ${fmt.money(s.cost)} · Tiền mặt ${fmt.money(s.cash)}`;
    el('pf-alloc').textContent = s.allocation_pct != null ? s.allocation_pct + '%' : '—';
    el('pf-alloc-bar').style.width = Math.min(100, s.allocation_pct || 0) + '%';
  }

  /* ----------------------------------------------------------- positions */

  function stopCell(p) {
    const stop = p.stop_loss != null ? p.stop_loss : p.suggested_stop;
    if (stop == null) return '<td class="num muted">—</td>';
    const hint = p.stop_loss == null ? '<span class="muted small" title="Gợi ý từ phân tích Fibonacci/ATR">*</span>' : '';
    return `<td class="num">${fmt.price(stop)}${hint}</td>`;
  }

  function renderPositions(positions) {
    const tbody = el('positions-full-table').querySelector('tbody');
    if (!positions.length) {
      tbody.innerHTML = '<tr class="no-hover"><td colspan="11"><div class="empty-state"><strong>Chưa có vị thế nào</strong>Bấm "+ Thêm vị thế" để ghi lại cổ phiếu đang nắm giữ — hệ thống sẽ cảnh báo khi có tín hiệu.</div></td></tr>';
      return;
    }
    tbody.innerHTML = positions.map((p) => {
      const distCls = p.stop_distance_pct != null && p.stop_distance_pct < 3 ? 'neg' : 'flat';
      return `<tr data-pos="${p.id}">
        <td><div class="sym-cell"><strong>${fmt.escape(p.symbol)}</strong><small>${fmt.escape(p.note || (p.buy_date ? 'Mua ' + p.buy_date : ''))}</small></div></td>
        <td class="num">${fmt.num(p.quantity)}</td>
        <td class="num">${fmt.price(p.avg_cost)}</td>
        <td class="num">${fmt.price(p.price)}</td>
        <td class="num">${fmt.money(p.value)}</td>
        <td class="num ${fmt.tone(p.pnl)}">${fmt.money(p.pnl)}</td>
        <td class="num ${fmt.tone(p.pnl_pct)}">${fmt.pct(p.pnl_pct)}</td>
        <td>${signalBadge(p.signal)}</td>
        ${stopCell(p)}
        <td class="num ${distCls}">${p.stop_distance_pct != null ? p.stop_distance_pct + '%' : '—'}</td>
        <td class="num">
          <button class="btn btn-xs btn-ghost" data-edit="${p.id}">Sửa</button>
          <button class="btn btn-xs btn-danger" data-del="${p.id}">Xóa</button>
        </td>
      </tr>`;
    }).join('');
    tbody.querySelectorAll('tr[data-pos]').forEach((tr) => {
      tr.addEventListener('click', (ev) => {
        if (ev.target.closest('button')) return;
        window.location.href = `/phan-tich?symbol=${encodeURIComponent(tr.querySelector('strong').textContent)}`;
      });
    });
    tbody.querySelectorAll('[data-edit]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const p = positions.find((x) => x.id === parseInt(btn.dataset.edit, 10));
        if (p) openPositionModal(p);
      });
    });
    tbody.querySelectorAll('[data-del]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const p = positions.find((x) => x.id === parseInt(btn.dataset.del, 10));
        if (p) confirmDelete(p);
      });
    });
  }

  /* ----------------------------------------------------------- watchlist */

  function renderWatchlist(rows) {
    const tbody = el('watch-table').querySelector('tbody');
    if (!rows.length) {
      tbody.innerHTML = '<tr class="no-hover"><td colspan="8"><div class="empty-state"><strong>Chưa theo dõi mã nào</strong>Thêm mã tiềm năng để nhận cảnh báo ngay khi xuất hiện điểm mua Fibonacci.</div></td></tr>';
      return;
    }
    tbody.innerHTML = rows.map((w) => {
      const zone = w.buy_zone && w.buy_zone.length > 1
        ? `${fmt.price(w.buy_zone[0])} – ${fmt.price(w.buy_zone[1])}` : '—';
      return `<tr data-watch="${w.id}">
        <td><strong>${fmt.escape(w.symbol)}</strong></td>
        <td class="num">${fmt.price(w.price)}</td>
        <td class="num ${fmt.tone(w.change_pct)}">${fmt.pct(w.change_pct)}</td>
        <td>${signalBadge(w.signal)}</td>
        <td class="num">${zone}</td>
        <td class="num">${w.target_price != null ? fmt.price(w.target_price) : '—'}</td>
        <td class="muted small">${fmt.escape(w.note || '')}</td>
        <td class="num"><button class="btn btn-xs btn-danger" data-unwatch="${w.id}">Bỏ</button></td>
      </tr>`;
    }).join('');
    tbody.querySelectorAll('tr[data-watch]').forEach((tr) => {
      tr.addEventListener('click', (ev) => {
        if (ev.target.closest('button')) return;
        window.location.href = `/phan-tich?symbol=${encodeURIComponent(tr.querySelector('strong').textContent)}`;
      });
    });
    tbody.querySelectorAll('[data-unwatch]').forEach((btn) => {
      btn.addEventListener('click', async () => {
        try {
          await fetchJSON(`/api/portfolio/watch/${btn.dataset.unwatch}`, { method: 'DELETE' });
          toast('Đã bỏ theo dõi.', 'success');
          loadOverview();
        } catch (err) { toast(err.message, 'error'); }
      });
    });
  }

  /* ---------------------------------------------------------- allocation */

  function renderAllocation(positions, summary) {
    const bar = el('alloc-bar');
    const legend = el('alloc-legend');
    const equity = summary.equity || 0;
    if (!positions.length || !equity) {
      bar.innerHTML = '<span style="width:100%;background:rgba(148,163,184,0.15)"></span>';
      legend.innerHTML = '<span class="muted small">Chưa có vị thế — toàn bộ vốn đang là tiền mặt.</span>';
      return;
    }
    const total = positions.reduce((acc, p) => acc + (p.value || 0), 0);
    let html = '';
    const items = positions.map((p, i) => {
      const pct = equity ? (p.value || 0) / equity * 100 : 0;
      const color = PALETTE[i % PALETTE.length];
      html += `<span style="width:${pct}%;background:${color}" title="${fmt.escape(p.symbol)}: ${pct.toFixed(1)}%"></span>`;
      return `<span class="legend-item"><span class="sw" style="background:${color}"></span>${fmt.escape(p.symbol)} · ${pct.toFixed(1)}% · ${fmt.money(p.value)}</span>`;
    });
    const cashPct = Math.max(0, 100 - (equity ? total / equity * 100 : 0));
    html += `<span style="width:${cashPct}%;background:rgba(148,163,184,0.18)" title="Tiền mặt: ${cashPct.toFixed(1)}%"></span>`;
    bar.innerHTML = html;
    legend.innerHTML = items.join('') +
      `<span class="legend-item"><span class="sw" style="background:rgba(148,163,184,0.4)"></span>Tiền mặt · ${cashPct.toFixed(1)}%</span>`;
  }

  /* ------------------------------------------------------------- alerts */

  function alertItem(a) {
    return `<div class="alert-item ${fmt.escape(a.severity)}">
      <div class="a-body">
        <div class="a-msg">${fmt.escape(a.message)}</div>
        <div class="a-meta"><span>${fmt.escape(a.symbol)}</span><span>${fmt.time(a.created_at)}</span></div>
      </div>
      <div class="a-actions"><button class="btn btn-xs btn-ghost" data-ack="${a.id}">Đã xem</button></div>
    </div>`;
  }

  async function loadAlerts() {
    try {
      const data = await fetchJSON('/api/alerts?limit=8');
      const feed = el('pf-alerts-feed');
      if (!data.alerts || !data.alerts.length) {
        feed.innerHTML = '<div class="empty-state" style="padding:20px;">Không có cảnh báo mới. Danh mục đang ổn định ✅</div>';
        return;
      }
      feed.innerHTML = data.alerts.map(alertItem).join('');
      feed.querySelectorAll('[data-ack]').forEach((btn) => {
        btn.addEventListener('click', async () => {
          try {
            await postJSON(`/api/alerts/${btn.dataset.ack}/ack`, {});
            App.refreshAlertCount();
            loadAlerts();
            loadOverview();
          } catch (err) { toast(err.message, 'error'); }
        });
      });
    } catch (err) { /* ignore */ }
  }

  /* ------------------------------------------------------------- modals */

  async function symbolSuggestions() {
    if (symbolCache) return symbolCache;
    try {
      const data = await fetchJSON('/api/symbols?limit=100');
      symbolCache = data.symbols || [];
    } catch (err) { symbolCache = []; }
    return symbolCache;
  }

  async function fillDatalist() {
    const list = el('modal-symbol-suggest');
    if (!list || list.dataset.loaded) return;
    const rows = await symbolSuggestions();
    list.innerHTML = rows.map((s) => `<option value="${fmt.escape(s.symbol)}">${fmt.escape(s.organ_short_name || '')}</option>`).join('');
    list.dataset.loaded = '1';
  }

  function openPositionModal(p) {
    const editing = !!p;
    const m = modal(`
      <h3>${editing ? 'Sửa vị thế ' + fmt.escape(p.symbol) : 'Thêm vị thế mới'}</h3>
      <div class="grid grid-2">
        <label class="field">Mã cổ phiếu
          <input class="input" id="m-symbol" list="modal-symbol-suggest" value="${editing ? fmt.escape(p.symbol) : ''}"
                 placeholder="FPT" ${editing ? 'disabled' : ''}>
          <datalist id="modal-symbol-suggest"></datalist>
        </label>
        <label class="field">Khối lượng (CP)
          <input class="input" type="number" id="m-qty" min="100" step="100" value="${editing ? p.quantity : ''}">
        </label>
        <label class="field">Giá vốn (đ)
          <input class="input" type="number" id="m-cost" min="0" step="50" value="${editing ? p.avg_cost : ''}">
        </label>
        <label class="field">Ngày mua
          <input class="input" type="date" id="m-date" value="${editing ? (p.buy_date || '') : ''}">
        </label>
        <label class="field">Cắt lỗ (đ) — để trống = theo phân tích
          <input class="input" type="number" id="m-stop" min="0" step="50" value="${editing && p.stop_loss != null ? p.stop_loss : ''}">
        </label>
        <label class="field">Chốt lời (đ) — tùy chọn
          <input class="input" type="number" id="m-take" min="0" step="50" value="${editing && p.take_profit != null ? p.take_profit : ''}">
        </label>
      </div>
      <label class="field mt-12">Ghi chú
        <input class="input" id="m-note" value="${editing ? fmt.escape(p.note || '') : ''}" placeholder="VD: mua theo tín hiệu Fib 61.8%">
      </label>
      ${editing ? `<label class="field mt-12">Trạng thái
        <select class="input" id="m-status">
          <option value="OPEN" ${p.status !== 'CLOSED' ? 'selected' : ''}>Đang nắm giữ</option>
          <option value="CLOSED" ${p.status === 'CLOSED' ? 'selected' : ''}>Đã đóng</option>
        </select></label>` : ''}
      <div class="flex mt-12">
        <button class="btn btn-ghost btn-sm" id="m-suggest">Gợi ý giá &amp; cắt lỗ theo phân tích</button>
        <span class="hint" id="m-suggest-note"></span>
      </div>
      <div class="modal-actions">
        <button class="btn btn-ghost" id="m-cancel">Hủy</button>
        <button class="btn btn-primary" id="m-save">${editing ? 'Lưu thay đổi' : 'Thêm vào danh mục'}</button>
      </div>`);

    const symInput = m.querySelector('#m-symbol');
    symInput.addEventListener('focus', fillDatalist);

    m.querySelector('#m-suggest').addEventListener('click', async () => {
      const sym = symInput.value.trim().toUpperCase();
      if (!sym) { toast('Nhập mã trước đã', 'warn'); return; }
      const note = m.querySelector('#m-suggest-note');
      note.textContent = 'Đang phân tích...';
      try {
        const p2 = await fetchJSON(`/api/analyze?symbol=${encodeURIComponent(sym)}`);
        if (!m.querySelector('#m-cost').value) m.querySelector('#m-cost').value = Math.round(p2.price);
        const stop = (p2.levels || {}).stop_loss;
        if (stop) m.querySelector('#m-stop').value = Math.round(stop);
        const target = ((p2.levels || {}).sell_points || [])[0];
        if (target && !m.querySelector('#m-take').value) m.querySelector('#m-take').value = Math.round(target.price);
        note.textContent = `Đã lấy: giá ${fmt.price(p2.price)} đ · cắt lỗ ${stop ? fmt.price(stop) + ' đ' : '—'} · tín hiệu ${p2.signal.label}`;
      } catch (err) {
        note.textContent = '';
        toast(err.message, 'error', 'Không lấy được phân tích');
      }
    });

    m.querySelector('#m-cancel').addEventListener('click', closeModal);
    m.querySelector('#m-save').addEventListener('click', async () => {
      const body = {
        symbol: symInput.value.trim().toUpperCase(),
        quantity: parseFloat(m.querySelector('#m-qty').value),
        avg_cost: parseFloat(m.querySelector('#m-cost').value),
        buy_date: m.querySelector('#m-date').value || undefined,
        stop_loss: parseFloat(m.querySelector('#m-stop').value) || null,
        take_profit: parseFloat(m.querySelector('#m-take').value) || null,
        note: m.querySelector('#m-note').value.trim(),
      };
      if (editing) body.status = m.querySelector('#m-status').value;
      if (!body.symbol || !body.quantity || !body.avg_cost) {
        toast('Nhập đủ mã, khối lượng và giá vốn', 'warn'); return;
      }
      try {
        if (editing) await postJSON(`/api/portfolio/positions/${p.id}`, body, 'PUT');
        else await postJSON('/api/portfolio/positions', body);
        closeModal();
        toast(editing ? 'Đã lưu thay đổi.' : `Đã thêm ${body.symbol} vào danh mục.`, 'success');
        loadOverview();
        if (!editing) {
          postJSON('/api/portfolio/scan', { force: true }).then(() => {
            App.refreshAlertCount(); loadAlerts();
          }).catch(() => {});
        }
      } catch (err) {
        toast(err.message, 'error', 'Không lưu được vị thế');
      }
    });
  }

  function confirmDelete(p) {
    const m = modal(`
      <h3>Xóa vị thế ${fmt.escape(p.symbol)}?</h3>
      <p class="muted">Vị thế ${fmt.num(p.quantity)} CP, giá vốn ${fmt.price(p.avg_cost)} đ sẽ bị xóa khỏi danh mục. Lịch sử cảnh báo vẫn được giữ.</p>
      <div class="modal-actions">
        <button class="btn btn-ghost" id="d-cancel">Hủy</button>
        <button class="btn btn-danger" id="d-ok">Xóa vị thế</button>
      </div>`);
    m.querySelector('#d-cancel').addEventListener('click', closeModal);
    m.querySelector('#d-ok').addEventListener('click', async () => {
      try {
        await fetchJSON(`/api/portfolio/positions/${p.id}`, { method: 'DELETE' });
        closeModal();
        toast(`Đã xóa ${p.symbol} khỏi danh mục.`, 'success');
        loadOverview();
      } catch (err) { toast(err.message, 'error'); }
    });
  }

  function openWatchModal() {
    const m = modal(`
      <h3>Thêm mã theo dõi</h3>
      <label class="field">Mã cổ phiếu
        <input class="input" id="w-symbol" list="modal-symbol-suggest2" placeholder="VCB">
        <datalist id="modal-symbol-suggest2"></datalist>
      </label>
      <div class="grid grid-2 mt-12">
        <label class="field">Giá mục tiêu (đ) — tùy chọn
          <input class="input" type="number" id="w-target" step="50" min="0">
        </label>
        <label class="field">Ghi chú
          <input class="input" id="w-note" placeholder="VD: chờ về vùng vàng Fib 0.618">
        </label>
      </div>
      <div class="modal-actions">
        <button class="btn btn-ghost" id="w-cancel">Hủy</button>
        <button class="btn btn-primary" id="w-save">Theo dõi</button>
      </div>`);
    const input = m.querySelector('#w-symbol');
    const list = m.querySelector('#modal-symbol-suggest2');
    input.addEventListener('focus', async () => {
      if (list.dataset.loaded) return;
      const rows = await symbolSuggestions();
      list.innerHTML = rows.map((s) => `<option value="${fmt.escape(s.symbol)}">${fmt.escape(s.organ_short_name || '')}</option>`).join('');
      list.dataset.loaded = '1';
    });
    m.querySelector('#w-cancel').addEventListener('click', closeModal);
    m.querySelector('#w-save').addEventListener('click', async () => {
      const symbol = input.value.trim().toUpperCase();
      if (!symbol) { toast('Nhập mã cổ phiếu', 'warn'); return; }
      try {
        await postJSON('/api/portfolio/watch', {
          symbol,
          target_price: parseFloat(m.querySelector('#w-target').value) || null,
          note: m.querySelector('#w-note').value.trim(),
        });
        closeModal();
        toast(`Đang theo dõi ${symbol} — sẽ cảnh báo khi có tín hiệu mua.`, 'success');
        loadOverview();
      } catch (err) { toast(err.message, 'error'); }
    });
  }

  /* ---------------------------------------------------------------- init */

  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.tabs .tab').forEach((tab) => {
      tab.addEventListener('click', () => {
        document.querySelectorAll('.tabs .tab').forEach((t) => t.classList.toggle('active', t === tab));
        el('panel-positions').classList.toggle('hidden', tab.dataset.panel !== 'panel-positions');
        el('panel-watch').classList.toggle('hidden', tab.dataset.panel !== 'panel-watch');
      });
    });
    el('add-pos-btn').addEventListener('click', () => openPositionModal(null));
    el('add-watch-btn').addEventListener('click', openWatchModal);
    el('pf-scan-btn').addEventListener('click', async () => {
      const btn = el('pf-scan-btn');
      btn.disabled = true;
      btn.textContent = 'Đang quét...';
      try {
        const res = await postJSON('/api/portfolio/scan', { force: true });
        toast(`Đã quét ${res.scanned} mã — ${res.created} cảnh báo cập nhật.`, 'success', 'Quét cảnh báo');
        App.refreshAlertCount();
        loadAlerts();
        loadOverview();
      } catch (err) {
        toast(err.message, 'error', 'Quét cảnh báo thất bại');
      } finally {
        btn.disabled = false;
        btn.textContent = 'Quét cảnh báo ngay';
      }
    });
    el('pf-ack-all').addEventListener('click', async () => {
      try {
        await postJSON('/api/alerts/ack-all', {});
        App.refreshAlertCount();
        loadAlerts();
        loadOverview();
        toast('Đã đánh dấu toàn bộ cảnh báo là đã xem.', 'success');
      } catch (err) { toast(err.message, 'error'); }
    });
    document.addEventListener('alerts-updated', () => { loadAlerts(); loadOverview(); });

    loadOverview();
    loadAlerts();
  });
})();
