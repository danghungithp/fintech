/* FinViet Pro — shared frontend utilities */
(function () {
  'use strict';

  const nf0 = new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 0 });
  const nf1 = new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 1 });
  const nf2 = new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 2 });

  const SIGNAL_CLASS = {
    STRONG_BUY: 'tone-up', BUY: 'tone-up',
    HOLD: 'tone-neutral',
    SELL: 'tone-down', STRONG_SELL: 'tone-down',
  };
  const SIGNAL_LABEL = {
    STRONG_BUY: 'MUA MẠNH', BUY: 'MUA', HOLD: 'NẮM GIỮ', SELL: 'BÁN', STRONG_SELL: 'BÁN MẠNH',
  };

  const fmt = {
    num(v, d = 0) {
      if (v === null || v === undefined || Number.isNaN(v)) return '—';
      const f = d === 2 ? nf2 : d === 1 ? nf1 : nf0;
      return f.format(v);
    },
    price(v) { return this.num(v, v !== null && Math.abs(v) < 100 ? 2 : 0); },
    pct(v, signed = true) {
      if (v === null || v === undefined || Number.isNaN(v)) return '—';
      const s = signed && v > 0 ? '+' : '';
      return s + nf2.format(v) + '%';
    },
    vol(v) {
      if (v === null || v === undefined) return '—';
      if (v >= 1e9) return nf2.format(v / 1e9) + ' tỷ';
      if (v >= 1e6) return nf2.format(v / 1e6) + ' tr';
      if (v >= 1e3) return nf0.format(v / 1e3) + ' N';
      return nf0.format(v);
    },
    money(v) {
      if (v === null || v === undefined) return '—';
      const abs = Math.abs(v);
      if (abs >= 1e9) return nf2.format(v / 1e9) + ' tỷ';
      if (abs >= 1e6) return nf1.format(v / 1e6) + ' tr';
      return nf0.format(v) + ' đ';
    },
    tone(v) { return v > 0 ? 'pos' : v < 0 ? 'neg' : 'flat'; },
    time(ts) { return ts ? String(ts).slice(11, 16) + ' ' + String(ts).slice(8, 10) + '/' + String(ts).slice(5, 7) : ''; },
    escape(s) {
      return String(s ?? '').replace(/[&<>"']/g, (c) => (
        { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
      ));
    },
  };

  async function fetchJSON(url, opts) {
    const res = await fetch(url, opts);
    let body = null;
    try { body = await res.json(); } catch (e) { /* non-JSON */ }
    if (!res.ok) {
      const msg = (body && (body.error || body.message)) || `Lỗi ${res.status}`;
      throw new Error(msg);
    }
    return body;
  }

  function postJSON(url, data, method = 'POST') {
    return fetchJSON(url, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data || {}),
    });
  }

  function toast(message, type = 'info', title = '', sticky = false) {
    const root = document.getElementById('toasts');
    if (!root) return;
    const div = document.createElement('div');
    div.className = `toast ${type}`;
    div.innerHTML = `${title ? `<strong>${fmt.escape(title)}</strong>` : ''}<small>${fmt.escape(message)}</small>`;
    root.appendChild(div);
    if (!sticky) setTimeout(() => div.remove(), type === 'error' ? 7000 : 4500);
  }

  function signalBadge(sig, extra = '') {
    if (!sig) return '<span class="badge tone-neutral">—</span>';
    const code = typeof sig === 'string' ? sig : sig.code;
    const label = (typeof sig === 'object' && sig.label) || SIGNAL_LABEL[code] || code;
    const strong = code === 'STRONG_BUY' || code === 'STRONG_SELL';
    return `<span class="badge ${SIGNAL_CLASS[code] || 'tone-neutral'} ${extra} ${strong ? 'strong' : ''}">${label}</span>`;
  }

  function scoreBar(score) {
    const s = Math.max(-100, Math.min(100, score || 0));
    const w = Math.abs(s) / 2;
    const left = s >= 0 ? 50 : 50 - w;
    const color = s > 25 ? 'var(--up)' : s < -25 ? 'var(--down)' : 'var(--warn)';
    return `<div class="score-bar"><span style="left:${left}%;width:${w}%;background:${color}"></span></div>`;
  }

  function severityBadge(sev) {
    return `<span class="sev-dot sev-${fmt.escape(sev || 'info')}"></span>`;
  }

  /* ---- global symbol search (topbar + datalist) */
  async function loadSymbolSuggestions(inputEl, listEl) {
    if (!inputEl || !listEl || listEl.dataset.loaded) return;
    try {
      const data = await fetchJSON('/api/symbols?limit=100');
      listEl.innerHTML = (data.symbols || [])
        .map((s) => `<option value="${fmt.escape(s.symbol)}">${fmt.escape(s.organ_short_name || s.exchange || '')}</option>`)
        .join('');
      listEl.dataset.loaded = '1';
    } catch (e) { /* offline is fine */ }
  }

  function setupGlobalSearch() {
    const form = document.getElementById('global-search');
    const input = document.getElementById('global-symbol-input');
    const list = document.getElementById('global-symbol-suggest');
    if (form && input) {
      form.addEventListener('submit', (ev) => {
        ev.preventDefault();
        const sym = input.value.trim().toUpperCase();
        if (sym) window.location.href = `/phan-tich?symbol=${encodeURIComponent(sym)}`;
      });
      input.addEventListener('focus', () => loadSymbolSuggestions(input, list));
    }
    setupDatalists();
    setupScanButton();
    refreshAlertCount();
    setInterval(refreshAlertCount, 60000);
    refreshAuthArea();
  }

  function setupDatalists() {
    document.querySelectorAll('input[data-symbol-input]').forEach((input) => {
      const listId = input.getAttribute('list');
      const list = listId ? document.getElementById(listId) : null;
      if (list) input.addEventListener('focus', () => loadSymbolSuggestions(input, list));
    });
  }

  async function refreshAlertCount() {
    try {
      const data = await fetchJSON('/api/alerts?limit=1');
      const count = data.unread || 0;
      ['top-alert-count', 'nav-alert-count'].forEach((id) => {
        const el = document.getElementById(id);
        if (el) {
          el.textContent = count > 99 ? '99+' : count;
          el.classList.toggle('hidden', count === 0 && id === 'nav-alert-count');
        }
      });
    } catch (e) { /* ignore */ }
  }

  function setupScanButton() {
    const btn = document.getElementById('top-scan-btn');
    if (!btn) return;
    btn.addEventListener('click', async () => {
      btn.disabled = true;
      btn.textContent = 'Đang quét...';
      try {
        const res = await postJSON('/api/portfolio/scan', { force: true });
        if (res.skipped) toast(res.reason, 'warn', 'Quét cảnh báo');
        else toast(`Đã quét ${res.scanned} mã, ${res.created} cảnh báo cập nhật.`, 'success', 'Quét cảnh báo');
        refreshAlertCount();
        document.dispatchEvent(new CustomEvent('alerts-updated'));
      } catch (err) {
        toast(err.message, 'error', 'Quét cảnh báo thất bại');
      } finally {
        btn.disabled = false;
        btn.textContent = 'Quét danh mục';
      }
    });
  }

  /* ---- auth chip (topbar): login/register when logged out, user + logout when in */
  async function refreshAuthArea() {
    const area = document.getElementById('auth-area');
    if (!area) return;
    let user = null;
    try {
      const data = await fetchJSON('/api/auth/me');
      user = data && data.user;
    } catch (e) { /* treat as logged out */ }
    if (user) {
      const name = user.name || user.email || 'Thành viên';
      area.innerHTML = `
        <a class="btn btn-ghost btn-sm" href="/so-giao-dich" title="Sổ giao dịch của bạn">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" width="15" height="15"><circle cx="12" cy="8" r="3.5"/><path d="M5 20a7 7 0 0 1 14 0"/></svg>
          ${fmt.escape(name)}
        </a>
        <button class="btn btn-ghost btn-sm" id="logout-btn" title="Đăng xuất">Thoát</button>`;
      area.querySelector('#logout-btn').addEventListener('click', async () => {
        try { await postJSON('/api/auth/logout', {}); } catch (e) { /* ignore */ }
        window.location.href = '/';
      });
    } else {
      area.innerHTML = `
        <a class="btn btn-ghost btn-sm" href="/dang-nhap">Đăng nhập</a>
        <a class="btn btn-primary btn-sm" href="/dang-ky">Đăng ký</a>`;
    }
  }

  function modal(html) {
    const root = document.getElementById('modal-root');
    root.innerHTML = `<div class="modal-backdrop"><div class="modal">${html}</div></div>`;
    root.querySelector('.modal-backdrop').addEventListener('click', (ev) => {
      if (ev.target === root.querySelector('.modal-backdrop')) closeModal();
    });
    return root.querySelector('.modal');
  }
  function closeModal() {
    const root = document.getElementById('modal-root');
    if (root) root.innerHTML = '';
  }

  document.addEventListener('DOMContentLoaded', setupGlobalSearch);

  window.App = { fmt, fetchJSON, postJSON, toast, signalBadge, scoreBar, severityBadge, modal, closeModal, refreshAlertCount };
})();
