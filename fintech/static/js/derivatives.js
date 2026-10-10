(function () {
  'use strict';
  const { fmt, fetchJSON, postJSON, toast, showState } = App;
  const el = (id) => document.getElementById(id);
  let currentSymbol = null;

  async function renderDerivatives(p) {
    if (p.symbol !== 'VN30F1M') {
      el('m-derivatives').classList.add('hidden');
      return;
    }
    el('m-derivatives').classList.remove('hidden');
    showState('m-derivatives', 'loading');
    
    const margin = parseFloat(el('deriv-margin').value) || 100000000;
    const max_loss = parseFloat(el('deriv-loss').value) || 1.0;
    
    try {
      const resp = await postJSON('/api/derivatives/calc', { margin, max_loss });
      
      const dz = el('deriv-danger-zone');
      if (resp.in_danger_zone) dz.classList.remove('hidden');
      else dz.classList.add('hidden');
      
      el('deriv-price').textContent = resp.price ? fmt.num(resp.price, 1) : '—';
      el('deriv-vwap').textContent = resp.vwap ? fmt.num(resp.vwap, 1) : '—';
      el('deriv-rsi').textContent = resp.rsi ? fmt.num(resp.rsi, 1) : '—';
      
      const pv = resp.pivots || {};
      el('deriv-pivots').textContent = pv.P ? `${fmt.num(pv.P, 1)} / ${fmt.num(pv.S1, 1)} / ${fmt.num(pv.R1, 1)}` : '—';
      
      const sig = el('deriv-signal');
      sig.textContent = resp.signal;
      sig.className = 'badge ' + (resp.signal === 'LONG' ? 'tone-up' : (resp.signal === 'SHORT' ? 'tone-down' : 'tone-info'));
      
      el('deriv-setup').textContent = resp.setup_name || '—';
      el('deriv-contracts').textContent = resp.max_contracts ? `${resp.max_contracts} HĐ (Rủi ro: ${fmt.money(resp.max_loss_vnd)})` : 'Đứng ngoài';
      el('deriv-stop').textContent = resp.stop_loss ? fmt.num(resp.stop_loss, 1) : '—';
      el('deriv-target').textContent = resp.target ? fmt.num(resp.target, 1) : '—';
      el('deriv-rr').textContent = resp.risk_reward ? `1 : ${resp.risk_reward}` : '—';
      
      showState('m-derivatives', 'body');
    } catch (err) {
      showState('m-derivatives', 'error');
      const errEl = el('m-derivatives').querySelector('.mod-error');
      if (errEl) errEl.textContent = err.message || 'Không phân tích được phái sinh.';
    }
  }

  async function analyze(symbol) {
    if (!symbol) return;
    symbol = symbol.toUpperCase();
    currentSymbol = symbol;
    window.history.replaceState(null, '', '?symbol=' + encodeURIComponent(symbol));
    renderDerivatives({symbol});
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
    
    if (el('deriv-recalc')) el('deriv-recalc').addEventListener('click', () => { if (currentSymbol) renderDerivatives({symbol: currentSymbol}); });

    if (!initial) { el('tool-symbol').value = 'VN30F1M'; analyze('VN30F1M'); }
        if (el('bt-end')) el('bt-end').value = '2026-10-10';
    el('bt-form').addEventListener('submit', (ev) => { ev.preventDefault(); runBacktest('derivatives'); });

    if (initial) {
      el('tool-symbol').value = initial;
      analyze(initial);
    }
  });
})();
