(function () {
  'use strict';
  const { fmt, fetchJSON, postJSON, toast, showState } = App;
  const el = (id) => document.getElementById(id);
  let currentSymbol = null;

  async function renderCanslim(p) {
    showState('m-canslim', 'loading');
    try {
      const resp = await postJSON('/api/canslim/calc', { symbol: p.symbol });
      
      const m = resp.market || {};
      el('canslim-market-status').textContent = m.status || '—';
      if (m.passed) {
        el('canslim-market-status').className = 'badge tone-up';
      } else {
        el('canslim-market-status').className = 'badge tone-down';
      }

      el('canslim-is-uptrend').textContent = m.is_uptrend ? 'Có (Giá > MA50 & MA200)' : 'Không';
      el('canslim-dist-days').textContent = m.distribution_days != null ? m.distribution_days + ' ngày' : '—';
      el('canslim-market-prices').textContent = m.current ? `${fmt.num(m.current)} / ${fmt.num(m.ma50)} / ${fmt.num(m.ma200)}` : '—';

      const pat = resp.pattern || {};
      el('canslim-pattern-name').textContent = pat.name || 'Không rõ ràng';
      el('canslim-pattern-depth').textContent = pat.depth_pct != null ? pat.depth_pct + '%' : '—';
      el('canslim-pivot').textContent = resp.pivot ? fmt.price(resp.pivot) : '—';

      el('canslim-price-pivot').textContent = resp.current_price && resp.pivot ? `${fmt.price(resp.current_price)} / ${fmt.price(resp.pivot)}` : '—';
      el('canslim-is-breakout').innerHTML = resp.is_breakout ? '<span class="pos">Đạt (Giá vượt Pivot)</span>' : 'Chưa đạt';
      
      const reqVol = resp.v20 ? resp.v20 * 1.5 : 0;
      el('canslim-vol-breakout').innerHTML = resp.vol_breakout 
        ? `<span class="pos">Đạt (${fmt.vol(resp.current_vol)} > ${fmt.vol(reqVol)})</span>` 
        : `Chưa đạt (${fmt.vol(resp.current_vol)} < ${fmt.vol(reqVol)})`;
      
      const bz = resp.buy_zone || [];
      const bzText = bz.length === 2 ? `${fmt.price(bz[0])} - ${fmt.price(bz[1])}` : '—';
      el('canslim-buy-zone').innerHTML = resp.in_buy_zone 
        ? `<span class="pos">Nằm trong vùng (${bzText})</span>` 
        : `Ngoài vùng (${bzText})`;

      el('canslim-is-fomo').innerHTML = resp.is_fomo ? '<span class="neg">Giá đã vượt quá xa điểm mua (+5%)</span>' : 'Không';
      
      const alertBox = el('canslim-buy-alert');
      if (resp.buy_trigger && m.passed && pat.name !== 'Không đạt chuẩn') {
        alertBox.classList.remove('hidden');
      } else {
        alertBox.classList.add('hidden');
      }

      el('canslim-stop-loss').textContent = resp.stop_loss ? fmt.price(resp.stop_loss) : '—';
      el('canslim-target').textContent = resp.target_profit ? fmt.price(resp.target_profit) : '—';

      showState('m-canslim', 'body');
    } catch (err) {
      showState('m-canslim', 'error');
      const errEl = el('m-canslim').querySelector('.mod-error');
      if (errEl) errEl.textContent = err.message || 'Không phân tích được CANSLIM.';
    }
  }

  async function analyze(symbol) {
    if (!symbol) return;
    symbol = symbol.toUpperCase();
    currentSymbol = symbol;
    window.history.replaceState(null, '', '?symbol=' + encodeURIComponent(symbol));
    renderCanslim({symbol});
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
    
    

        if (el('bt-end')) el('bt-end').value = '2026-10-10';
    el('bt-form').addEventListener('submit', (ev) => { ev.preventDefault(); runBacktest('canslim'); });

    if (initial) {
      el('tool-symbol').value = initial;
      analyze(initial);
    }
  });
})();
