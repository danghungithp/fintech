/* FinViet Pro — settings page */
(function () {
  'use strict';
  const { fmt, fetchJSON, postJSON, toast } = App;
  const el = (id) => document.getElementById(id);

  const FIELD_MAP = {
    's-equity': 'equity',
    's-kelly-mode': 'kelly_mode',
    's-risk': 'risk_pct',
    's-maxpos': 'max_position_pct',
    's-lot': 'lot',
    's-history-days': 'history_days',
    's-cache-hours': 'cache_hours',
    's-scan-minutes': 'scan_minutes',
    's-max-symbols': 'screener_max_symbols',
    's-min-volume': 'min_avg_volume',
  };

  async function loadSettings() {
    try {
      const s = await fetchJSON('/api/settings');
      Object.entries(FIELD_MAP).forEach(([id, key]) => {
        const node = el(id);
        if (node && s[key] != null) node.value = s[key];
      });
    } catch (err) {
      toast(err.message, 'error', 'Không tải được cài đặt');
    }
  }

  async function saveSettings() {
    const body = {};
    Object.entries(FIELD_MAP).forEach(([id, key]) => {
      const node = el(id);
      if (!node) return;
      if (key === 'kelly_mode') body[key] = node.value;
      else if (node.value !== '') body[key] = node.value;
    });
    const btn = el('s-save');
    btn.disabled = true;
    btn.textContent = 'Đang lưu...';
    try {
      const res = await postJSON('/api/settings', body);
      toast(`Đã lưu ${Object.keys(res.updated || {}).length} cài đặt.`, 'success', 'Cài đặt');
    } catch (err) {
      toast(err.message, 'error', 'Không lưu được cài đặt');
    } finally {
      btn.disabled = false;
      btn.textContent = 'Lưu cài đặt';
    }
  }

  async function refreshSymbols() {
    const btn = el('s-refresh-symbols');
    const note = el('s-symbols-note');
    btn.disabled = true;
    btn.textContent = 'Đang đồng bộ...';
    note.textContent = 'Đang tải danh sách mã từ Vietcap (có thể mất vài giây)...';
    try {
      const res = await postJSON('/api/symbols/refresh', {});
      note.textContent = `Đồng bộ thành công — ${res.updated} mã trong SQLite.`;
      toast('Đã làm mới danh sách mã niêm yết.', 'success', 'Vietcap');
    } catch (err) {
      note.textContent = '';
      toast(err.message, 'error', 'Đồng bộ thất bại');
    } finally {
      btn.disabled = false;
      btn.textContent = 'Làm mới danh sách mã từ Vietcap';
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    el('s-save').addEventListener('click', saveSettings);
    el('s-reload').addEventListener('click', () => {
      loadSettings();
      toast('Đã khôi phục giá trị đang lưu.', 'info');
    });
    el('s-refresh-symbols').addEventListener('click', refreshSymbols);
    loadSettings();
  });
})();
