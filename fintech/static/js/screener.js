/* FinViet Pro — screener page */
(function () {
  'use strict';
  const { fmt, fetchJSON, postJSON, toast, signalBadge } = App;
  const el = (id) => document.getElementById(id);

  let universeType = 'group';
  let currentRunId = null;
  let pollTimer = null;

  const STATUS_META = {
    RUNNING: { label: 'Đang chạy', cls: 'tone-info' },
    DONE: { label: 'Hoàn tất', cls: 'tone-up' },
    ERROR: { label: 'Lỗi', cls: 'tone-down' },
  };

  /* ------------------------------------------------------------ universe */

  async function loadUniverses() {
    try {
      const data = await fetchJSON('/api/screener/universes');
      const groupSel = el('universe-group');
      groupSel.innerHTML = (data.groups || [])
        .map((g) => `<option value="${fmt.escape(g.code)}">${fmt.escape(g.name)}</option>`).join('');
      const exSel = el('universe-exchange');
      exSel.innerHTML = (data.exchanges || [])
        .map((x) => `<option value="${fmt.escape(x)}">${fmt.escape(x)}</option>`).join('');
    } catch (err) {
      toast(err.message, 'error', 'Không tải được danh sách nhóm');
    }
  }

  function setupTabs() {
    el('universe-tabs').querySelectorAll('.tab').forEach((tab) => {
      tab.addEventListener('click', () => {
        universeType = tab.dataset.type;
        el('universe-tabs').querySelectorAll('.tab').forEach((t) => t.classList.toggle('active', t === tab));
        el('group-wrap').classList.toggle('hidden', universeType !== 'group');
        el('exchange-wrap').classList.toggle('hidden', universeType !== 'exchange');
        el('custom-wrap').classList.toggle('hidden', universeType !== 'custom');
      });
    });
  }

  /* --------------------------------------------------------------- run */

  function collectUniverse() {
    if (universeType === 'group') return { type: 'group', value: el('universe-group').value };
    if (universeType === 'exchange') return { type: 'exchange', value: el('universe-exchange').value };
    const raw = el('universe-custom').value.trim();
    if (!raw) throw new Error('Vui lòng nhập danh sách mã cổ phiếu');
    return { type: 'custom', value: raw };
  }

  function collectCriteria() {
    const signals = Array.from(el('crit-signals').querySelectorAll('input:checked')).map((i) => i.value);
    if (!signals.length) throw new Error('Chọn ít nhất một loại tín hiệu');
    const num = (id) => {
      const v = parseFloat(el(id).value);
      return Number.isNaN(v) ? null : v;
    };
    return {
      signals,
      min_score: num('crit-min-score'),
      min_dividend_yield: num('crit-div-yield'),
      exclude_unknown_dividend: el('crit-exclude-unknown').checked,
      min_avg_volume: num('crit-min-volume'),
      price_min: num('crit-price-min'),
      price_max: num('crit-price-max'),
      max_symbols: num('crit-max-symbols'),
    };
  }

  async function startRun() {
    let universe, criteria;
    try {
      universe = collectUniverse();
      criteria = collectCriteria();
    } catch (err) {
      toast(err.message, 'warn', 'Thiếu tiêu chí');
      return;
    }
    const btn = el('run-btn');
    btn.disabled = true;
    btn.textContent = 'Đang khởi động...';
    try {
      const res = await postJSON('/api/screener/run', { universe, criteria });
      toast('Phiên sàng lọc đã bắt đầu — theo dõi tiến độ phía dưới.', 'success', 'Sàng lọc');
      showProgress(res.run_id);
      pollRun(res.run_id);
      loadRecentRuns();
    } catch (err) {
      toast(err.message, 'error', 'Không chạy được sàng lọc');
    } finally {
      btn.disabled = false;
      btn.textContent = 'Bắt đầu sàng lọc';
    }
  }

  /* ----------------------------------------------------------- progress */

  function showProgress(runId) {
    currentRunId = runId;
    el('run-progress').classList.remove('hidden');
    el('run-bar').style.width = '0%';
    el('run-status-label').textContent = 'Đang chuẩn bị danh sách mã...';
    el('run-stats').textContent = '—';
    el('run-matched').textContent = '0 mã đạt tiêu chí';
  }

  function stopPolling() {
    if (pollTimer) { clearTimeout(pollTimer); pollTimer = null; }
  }

  async function pollRun(runId) {
    stopPolling();
    try {
      const run = await fetchJSON(`/api/screener/runs/${runId}`);
      const total = run.total || 0;
      const processed = run.processed || 0;
      el('run-bar').style.width = `${run.progress_pct || 0}%`;
      el('run-stats').textContent = total
        ? `Đã xử lý ${processed}/${total} mã · lỗi ${run.failed || 0}`
        : 'Đang tải danh sách mã...';
      if (run.status === 'RUNNING') {
        el('run-status-label').textContent = 'Đang sàng lọc...';
        pollTimer = setTimeout(() => pollRun(runId), 1300);
        return;
      }
      // finished
      el('run-status-label').textContent = run.status === 'DONE'
        ? 'Sàng lọc hoàn tất' : 'Sàng lọc gặp lỗi';
      if (run.status === 'ERROR') {
        toast(run.error || 'Phiên sàng lọc thất bại', 'error', 'Sàng lọc');
      }
      const results = await fetchJSON(`/api/screener/runs/${runId}/results`);
      el('run-matched').textContent = `${(results.results || []).length} mã đạt tiêu chí`;
      renderResults(runId, run, results.results || []);
      loadRecentRuns();
    } catch (err) {
      stopPolling();
      toast(err.message, 'error', 'Mất kết nối theo dõi tiến độ');
    }
  }

  /* ------------------------------------------------------------ results */

  function zoneText(low, high) {
    return (low && high) ? `${fmt.price(low)} – ${fmt.price(high)}` : '—';
  }

  function renderResults(runId, run, rows) {
    const sub = el('results-sub');
    const uni = run.universe || {};
    const uniText = uni.type === 'group' ? `Nhóm ${uni.value}`
      : uni.type === 'exchange' ? `Sàn ${uni.value}` : 'Danh sách tự chọn';
    sub.textContent = `Phiên #${runId} · ${uniText} · ${fmt.time(run.finished_at || run.created_at || '')} · ${rows.length} mã đạt tiêu chí`;

    const exportBtn = el('export-btn');
    exportBtn.href = `/api/screener/runs/${runId}/export`;
    exportBtn.classList.remove('hidden');

    const tbody = el('results-table').querySelector('tbody');
    if (!rows.length) {
      tbody.innerHTML = '<tr class="no-hover"><td colspan="12"><div class="empty-state"><strong>Không có mã nào đạt tiêu chí</strong>Thử nới lỏng điều kiện (giảm điểm tối thiểu, bỏ lọc cổ tức...) hoặc chọn nhóm lớn hơn.</div></td></tr>';
      return;
    }
    tbody.innerHTML = rows.map((r) => `
      <tr onclick="window.location='/phan-tich?symbol=${encodeURIComponent(r.symbol)}'" title="${fmt.escape((r.reasons || []).join(' · '))}">
        <td><strong>${fmt.escape(r.symbol)}</strong></td>
        <td>${signalBadge(r.signal, r.signal_label)}</td>
        <td class="num ${fmt.tone(r.score)}">${r.score > 0 ? '+' : ''}${r.score ?? '—'}</td>
        <td class="num">${fmt.price(r.price)}</td>
        <td class="num ${fmt.tone(r.change_pct)}">${fmt.pct(r.change_pct)}</td>
        <td class="num">${r.rsi != null ? fmt.num(r.rsi, 1) : '—'}</td>
        <td class="num">${fmt.vol(r.avg_volume)}</td>
        <td class="num ${r.dividend_yield != null ? 'pos' : ''}">${r.dividend_yield != null ? r.dividend_yield + '%' : '—'}</td>
        <td class="num">${zoneText(r.buy_zone_low, r.buy_zone_high)}</td>
        <td class="num neg">${fmt.price(r.stop_loss)}</td>
        <td class="num pos">${fmt.price(r.target1)}</td>
        <td class="num">${r.risk_reward != null ? r.risk_reward + '×' : '—'}</td>
      </tr>`).join('');
  }

  /* --------------------------------------------------------- recent runs */

  function uniLabel(run) {
    const uni = run.universe || {};
    if (uni.type === 'group') return `Nhóm ${uni.value}`;
    if (uni.type === 'exchange') return `Sàn ${uni.value}`;
    const raw = Array.isArray(uni.value) ? uni.value.join(', ') : String(uni.value || '');
    return raw.length > 42 ? raw.slice(0, 42) + '...' : raw || 'Tự chọn';
  }

  function runItem(run) {
    const meta = STATUS_META[run.status] || STATUS_META.DONE;
    const criteria = run.criteria || {};
    const chips = [];
    if (criteria.min_dividend_yield > 0) chips.push(`Cổ tức ≥ ${criteria.min_dividend_yield}%`);
    if (criteria.signals && criteria.signals.length) chips.push(criteria.signals.length > 2 ? 'Mọi tín hiệu' : criteria.signals.map((s) => ({ STRONG_BUY: 'MUA MẠNH', BUY: 'MUA', HOLD: 'GIỮ', SELL: 'BÁN', STRONG_SELL: 'BÁN MẠNH' }[s] || s)).join(', '));
    return `<div class="alert-item" data-run="${run.id}" style="cursor:pointer;border-left-color:${run.status === 'RUNNING' ? 'var(--info)' : run.status === 'ERROR' ? 'var(--down)' : 'var(--up)'};">
      <div class="a-body">
        <div class="a-msg"><b>Phiên #${run.id}</b> · ${fmt.escape(uniLabel(run))} — <b>${run.matched ?? 0}</b> mã đạt tiêu chí</div>
        <div class="a-meta">
          <span class="badge ${meta.cls}" style="padding:1px 7px;font-size:10.5px;">${meta.label}</span>
          <span>${fmt.time(run.finished_at || run.created_at || '')}</span>
          ${chips.length ? `<span>${fmt.escape(chips.join(' · '))}</span>` : ''}
        </div>
      </div>
      <div class="a-actions"><button class="btn btn-xs btn-ghost" data-view="${run.id}">Xem</button></div>
    </div>`;
  }

  async function loadRecentRuns() {
    try {
      const data = await fetchJSON('/api/screener/runs?limit=12');
      const runs = data.runs || [];
      const box = el('recent-runs');
      if (!runs.length) {
        box.innerHTML = '<div class="empty-state" style="padding:20px;">Chưa có phiên sàng lọc nào.</div>';
        return;
      }
      box.innerHTML = runs.map(runItem).join('');
      box.querySelectorAll('[data-run]').forEach((node) => {
        node.addEventListener('click', () => viewRun(parseInt(node.dataset.run, 10)));
      });
      return runs;
    } catch (err) {
      el('recent-runs').innerHTML = '<div class="empty-state" style="padding:20px;">Không tải được lịch sử.</div>';
      return [];
    }
  }

  async function viewRun(runId) {
    try {
      const run = await fetchJSON(`/api/screener/runs/${runId}`);
      if (run.status === 'RUNNING') {
        showProgress(runId);
        pollRun(runId);
        return;
      }
      const results = await fetchJSON(`/api/screener/runs/${runId}/results`);
      renderResults(runId, run, results.results || []);
      el('run-progress').classList.add('hidden');
      window.scrollTo({ top: 0, behavior: 'smooth' });
    } catch (err) {
      toast(err.message, 'error', 'Không xem được phiên sàng lọc');
    }
  }

  /* ---------------------------------------------------------------- init */

  document.addEventListener('DOMContentLoaded', async () => {
    const user = await App.getUser();
    if (!user) return; // keep the lock card visible

    el('screener-locked').classList.add('hidden');
    el('screener-app').classList.remove('hidden');

    setupTabs();
    el('run-btn').addEventListener('click', startRun);
    el('refresh-runs-btn').addEventListener('click', loadRecentRuns);
    await loadUniverses();
    const runs = await loadRecentRuns();
    const urlRun = parseInt(new URL(window.location.href).searchParams.get('run') || '', 10);
    if (urlRun) { viewRun(urlRun); return; }
    const latest = (runs || [])[0];
    if (latest) {
      if (latest.status === 'RUNNING') { showProgress(latest.id); pollRun(latest.id); }
      else viewRun(latest.id);
    }
  });
})();
