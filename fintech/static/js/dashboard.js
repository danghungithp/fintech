/* FinViet Pro — dashboard page */
(function () {
  'use strict';
  const { fmt, fetchJSON, postJSON, toast, signalBadge } = App;
  const el = (id) => document.getElementById(id);

  async function loadIndices() {
    try {
      const data = await fetchJSON('/api/index/summary');
      (data.indices || []).forEach((idx) => {
        const key = idx.symbol.toLowerCase();
        const priceEl = el(`idx-${key}-price`);
        const chgEl = el(`idx-${key}-change`);
        if (!priceEl) return;
        priceEl.textContent = idx.price != null ? fmt.num(idx.price, 2) : '—';
        chgEl.textContent = fmt.pct(idx.change_pct);
        chgEl.className = 'delta tnum ' + fmt.tone(idx.change_pct);
        const spark = el(`idx-${key}-spark`);
        if (spark && idx.spark && idx.spark.length) {
          Charts.renderSparkline(spark, idx.spark, (idx.change_pct || 0) >= 0 ? '#16c784' : '#ef4b5e');
        }
      });
    } catch (err) {
      ['idx-vnindex-price', 'idx-vn30-price'].forEach((id) => { el(id).textContent = '—'; });
    }
  }

  async function loadPortfolio() {
    const user = await App.getUser();
    if (!user) {
      el('stat-portfolio-value').textContent = '—';
      const pnlEl = el('stat-portfolio-pnl');
      pnlEl.textContent = 'Đăng nhập để xem danh mục của bạn';
      pnlEl.className = 'delta tnum muted';
      document.querySelector('#positions-table tbody').innerHTML =
        '<tr class="no-hover"><td colspan="8" class="muted">🔒 Quản lý danh mục dành cho thành viên — <a href="/dang-nhap?next=%2Fdanh-muc">đăng nhập</a> để thêm vị thế và theo dõi lãi/lỗ.</td></tr>';
      return;
    }
    try {
      const data = await fetchJSON('/api/portfolio/overview');
      const s = data.summary || {};
      el('stat-portfolio-value').textContent = s.positions ? fmt.money(s.market_value) : '0 đ';
      const pnlEl = el('stat-portfolio-pnl');
      pnlEl.textContent = s.positions
        ? `${fmt.money(s.pnl)} (${fmt.pct(s.pnl_pct)})`
        : 'Chưa có vị thế — thêm ở mục Danh mục';
      pnlEl.className = 'delta tnum ' + (s.positions ? fmt.tone(s.pnl) : 'muted');

      const tbody = document.querySelector('#positions-table tbody');
      const positions = data.positions || [];
      if (!positions.length) {
        tbody.innerHTML = '<tr class="no-hover"><td colspan="8" class="muted">Chưa có cổ phiếu nào trong danh mục. Vào <b>Danh mục đầu tư</b> để thêm vị thế.</td></tr>';
        return;
      }
      tbody.innerHTML = positions.map((p) => `
        <tr onclick="window.location='/phan-tich?symbol=${p.symbol}'">
          <td><div class="sym-cell"><strong>${p.symbol}</strong><small>${fmt.escape(p.note || '')}</small></div></td>
          <td class="num">${fmt.num(p.quantity)}</td>
          <td class="num">${fmt.price(p.avg_cost)}</td>
          <td class="num">${fmt.price(p.price)}</td>
          <td class="num ${fmt.tone(p.pnl)}">${fmt.money(p.pnl)}</td>
          <td class="num ${fmt.tone(p.pnl_pct)}">${fmt.pct(p.pnl_pct)}</td>
          <td>${signalBadge(p.signal)}</td>
          <td class="num ${p.stop_distance_pct != null && p.stop_distance_pct < 3 ? 'neg' : ''}">${fmt.price(p.stop_loss)}</td>
        </tr>`).join('');
    } catch (err) {
      toast(err.message, 'error', 'Không tải được danh mục');
    }
  }

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
      el('stat-alerts').textContent = data.unread || 0;
      el('stat-alerts').className = 'value tnum ' + (data.unread ? 'neg' : 'pos');
      const feed = el('alerts-feed');
      if (!data.alerts || !data.alerts.length) {
        feed.innerHTML = '<div class="empty-state" style="padding:20px;">Không có cảnh báo mới. Danh mục đang ổn định ✅</div>';
        return;
      }
      feed.innerHTML = data.alerts.map(alertItem).join('');
      feed.querySelectorAll('[data-ack]').forEach((btn) => {
        btn.addEventListener('click', async (ev) => {
          ev.stopPropagation();
          try {
            await postJSON(`/api/alerts/${btn.dataset.ack}/ack`, {});
            App.refreshAlertCount();
            loadAlerts();
          } catch (err) { toast(err.message, 'error'); }
        });
      });
    } catch (err) { /* ignore */ }
  }

  async function loadRecent() {
    try {
      const data = await fetchJSON('/api/analysis/recent?limit=8');
      const tbody = document.querySelector('#recent-table tbody');
      const items = data.items || [];
      if (!items.length) {
        tbody.innerHTML = '<tr class="no-hover"><td colspan="5" class="muted">Chưa có phân tích nào. Thử phân tích một mã ở ô phía trên.</td></tr>';
        return;
      }
      tbody.innerHTML = items.map((a) => `
        <tr onclick="window.location='/phan-tich?symbol=${a.symbol}'">
          <td><strong>${a.symbol}</strong></td>
          <td>${signalBadge(a.signal)}</td>
          <td class="num">${a.score > 0 ? '+' : ''}${a.score ?? '—'}</td>
          <td class="num">${fmt.price(a.price)}</td>
          <td class="muted small">${fmt.time(a.created_at)}</td>
        </tr>`).join('');
    } catch (err) { /* ignore */ }
  }

  async function loadTopSignals() {
    const user = await App.getUser();
    if (!user) {
      el('topsignals-sub').textContent = 'Dành cho thành viên';
      document.querySelector('#topsignals-table tbody').innerHTML =
        '<tr class="no-hover"><td colspan="7" class="muted">🔒 Danh sách mã đạt tiêu chí dành cho thành viên — <a href="/dang-nhap?next=%2Fsang-loc">đăng nhập</a> để dùng sàng lọc cổ phiếu.</td></tr>';
      return;
    }
    try {
      const runs = await fetchJSON('/api/screener/runs?limit=1');
      const run = (runs.runs || [])[0];
      const tbody = document.querySelector('#topsignals-table tbody');
      if (!run) {
        el('topsignals-sub').textContent = 'Chưa có phiên sàng lọc nào';
        tbody.innerHTML = '<tr class="no-hover"><td colspan="7" class="muted">Chạy <b>Sàng lọc cổ phiếu</b> để tìm cơ hội mua theo Fibonacci &amp; cổ tức.</td></tr>';
        return;
      }
      el('topsignals-sub').textContent = `Phiên #${run.id} · ${fmt.time(run.finished_at || run.created_at)} · ${run.matched || 0} mã đạt tiêu chí`;
      const res = await fetchJSON(`/api/screener/runs/${run.id}/results`);
      const rows = (res.results || []).slice(0, 6);
      if (!rows.length) {
        tbody.innerHTML = '<tr class="no-hover"><td colspan="7" class="muted">Lần sàng lọc gần nhất chưa có mã nào đạt tiêu chí.</td></tr>';
        return;
      }
      tbody.innerHTML = rows.map((r) => `
        <tr onclick="window.location='/phan-tich?symbol=${r.symbol}'">
          <td><strong>${r.symbol}</strong></td>
          <td>${signalBadge(r.signal, r.signal_label)}</td>
          <td class="num">${r.score > 0 ? '+' : ''}${r.score}</td>
          <td class="num">${fmt.price(r.price)}</td>
          <td class="num ${fmt.tone(r.change_pct)}">${fmt.pct(r.change_pct)}</td>
          <td class="num ${r.dividend_yield ? 'pos' : ''}">${r.dividend_yield != null ? r.dividend_yield + '%' : '—'}</td>
          <td class="num">${r.buy_zone_low && r.buy_zone_high ? `${fmt.price(r.buy_zone_low)} – ${fmt.price(r.buy_zone_high)}` : '—'}</td>
        </tr>`).join('');
    } catch (err) { /* ignore */ }
  }

  async function autoScan() {
    const user = await App.getUser();
    if (!user) return;
    try {
      const res = await postJSON('/api/portfolio/scan', {});
      if (!res.skipped && res.created > 0) {
        toast(`Tự động quét: ${res.created} cảnh báo được cập nhật.`, 'warn', 'Cảnh báo danh mục');
        loadAlerts();
        App.refreshAlertCount();
      }
    } catch (err) { /* silent */ }
  }

  document.addEventListener('DOMContentLoaded', () => {
    el('quick-form').addEventListener('submit', (ev) => {
      ev.preventDefault();
      const sym = el('quick-symbol').value.trim().toUpperCase();
      if (sym) window.location.href = `/phan-tich?symbol=${encodeURIComponent(sym)}`;
    });
    el('ack-all-btn').addEventListener('click', async () => {
      try {
        await postJSON('/api/alerts/ack-all', {});
        App.refreshAlertCount();
        loadAlerts();
        toast('Đã đánh dấu toàn bộ cảnh báo là đã xem.', 'success');
      } catch (err) { toast(err.message, 'error'); }
    });
    loadIndices();
    loadPortfolio();
    loadAlerts();
    loadRecent();
    loadTopSignals();
    autoScan();
  });
})();
