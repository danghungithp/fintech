/* FinViet Pro — alerts page */
(function () {
  'use strict';
  const { fmt, fetchJSON, postJSON, toast } = App;
  const el = (id) => document.getElementById(id);

  let filter = 'unread';
  let allAlerts = [];
  let unread = 0;

  const TYPE_LABEL = {
    STOP_LOSS: 'Cắt lỗ',
    SELL_SIGNAL: 'Tín hiệu bán',
    SELL_SIGNAL_WATCH: 'Tín hiệu bán (theo dõi)',
    TAKE_PROFIT: 'Chốt lời',
    ADD_SIGNAL: 'Gia tăng vị thế',
    TRAILING_STOP: 'Chốt lãi chủ động',
    SUPPORT_BREAK: 'Thủng hỗ trợ',
    BUY_SIGNAL: 'Tín hiệu mua',
    WATCH_TARGET: 'Đạt giá mục tiêu',
  };

  function typeBadge(a) {
    const cls = { critical: 'tone-down', high: 'tone-down', warning: 'tone-warn', medium: 'tone-info', info: 'tone-up' }[a.severity] || 'tone-neutral';
    return `<span class="badge ${cls}" style="padding:2px 8px;font-size:10.5px;">${fmt.escape(TYPE_LABEL[a.type] || a.type)}</span>`;
  }

  function renderFeed() {
    const sev = el('al-severity').value;
    const sym = el('al-symbol-filter-toggle').checked ? el('al-symbol-filter').value.trim().toUpperCase() : '';
    const rows = allAlerts.filter((a) =>
      (!sev || a.severity === sev) && (!sym || a.symbol.includes(sym)));

    const feed = el('al-feed');
    if (!rows.length) {
      feed.innerHTML = `<div class="empty-state"><strong>Không có cảnh báo nào</strong>${filter === 'unread' ? 'Danh mục đang ổn định — các cảnh báo đã xử lý nằm ở tab "Tất cả".' : 'Thử đổi bộ lọc hoặc bấm "Quét ngay".'}</div>`;
      return;
    }
    feed.innerHTML = rows.map((a) => `
      <div class="alert-item ${fmt.escape(a.severity)}">
        <div class="a-body">
          <div class="a-msg">${typeBadge(a)} <span style="margin-left:4px;">${fmt.escape(a.message)}</span></div>
          <div class="a-meta">
            <a href="/phan-tich?symbol=${encodeURIComponent(a.symbol)}" style="color:var(--accent);">${fmt.escape(a.symbol)} → phân tích</a>
            <span>${fmt.time(a.created_at)}</span>
            ${a.acknowledged ? '<span class="muted">· đã xem</span>' : ''}
          </div>
        </div>
        ${a.acknowledged ? '' : `<div class="a-actions"><button class="btn btn-xs btn-ghost" data-ack="${a.id}">Đã xem</button></div>`}
      </div>`).join('');

    feed.querySelectorAll('[data-ack]').forEach((btn) => {
      btn.addEventListener('click', async () => {
        try {
          const res = await postJSON(`/api/alerts/${btn.dataset.ack}/ack`, {});
          unread = res.unread ?? unread;
          el('al-unread-count').textContent = unread;
          App.refreshAlertCount();
          if (filter === 'unread') loadAlerts(); else {
            const a = allAlerts.find((x) => x.id === parseInt(btn.dataset.ack, 10));
            if (a) a.acknowledged = 1;
            renderFeed();
          }
        } catch (err) { toast(err.message, 'error'); }
      });
    });
  }

  async function loadAlerts() {
    try {
      const url = filter === 'all' ? '/api/alerts?include_ack=1&limit=300' : '/api/alerts?limit=300';
      const data = await fetchJSON(url);
      allAlerts = data.alerts || [];
      unread = data.unread || 0;
      el('al-unread-count').textContent = unread;
      renderFeed();
    } catch (err) {
      el('al-feed').innerHTML = `<div class="empty-state"><strong>Không tải được cảnh báo</strong>${fmt.escape(err.message)}</div>`;
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.tabs .tab').forEach((tab) => {
      tab.addEventListener('click', () => {
        filter = tab.dataset.filter;
        document.querySelectorAll('.tabs .tab').forEach((t) => t.classList.toggle('active', t === tab));
        loadAlerts();
      });
    });
    el('al-severity').addEventListener('change', renderFeed);
    el('al-symbol-filter-toggle').addEventListener('change', (ev) => {
      el('al-symbol-filter').classList.toggle('hidden', !ev.target.checked);
      if (ev.target.checked) el('al-symbol-filter').focus();
      renderFeed();
    });
    el('al-symbol-filter').addEventListener('input', renderFeed);

    el('al-ack-all').addEventListener('click', async () => {
      try {
        await postJSON('/api/alerts/ack-all', {});
        App.refreshAlertCount();
        toast('Đã đánh dấu toàn bộ cảnh báo là đã xem.', 'success');
        loadAlerts();
      } catch (err) { toast(err.message, 'error'); }
    });

    el('al-scan-btn').addEventListener('click', async () => {
      const btn = el('al-scan-btn');
      btn.disabled = true;
      btn.textContent = 'Đang quét...';
      try {
        const res = await postJSON('/api/portfolio/scan', { force: true });
        toast(`Đã quét ${res.scanned} mã — ${res.created} cảnh báo cập nhật.`, 'success', 'Quét cảnh báo');
        App.refreshAlertCount();
        loadAlerts();
      } catch (err) {
        toast(err.message, 'error', 'Quét cảnh báo thất bại');
      } finally {
        btn.disabled = false;
        btn.textContent = 'Quét ngay';
      }
    });

    document.addEventListener('alerts-updated', loadAlerts);
    loadAlerts();
  });
})();
