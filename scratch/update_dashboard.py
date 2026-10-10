import sys
sys.stdout.reconfigure(encoding='utf-8')
with open('fintech/static/js/dashboard.js', 'r', encoding='utf-8') as f:
    content = f.read()

new_func = """  async function loadMarketAnalysis() {
    const user = await App.getUser();
    if (!user) return;
    
    const sec = el('dashboard-market-analysis');
    if (!sec) return;
    sec.classList.remove('hidden');
    
    const grid = el('market-analysis-grid');
    const symbols = ['VNINDEX', 'VN30', 'VN30F1M'];
    const cards = [];
    
    for (const sym of symbols) {
      try {
        const data = await fetchJSON(`/api/analyze?symbol=${sym}`);
        const s = data.signal || {};
        const tf = data.trend_following || {};
        const ind = data.indicators || {};
        
        let tfBadge = '—';
        if (tf.step5_trailing_stop) {
           const tone = tf.step5_trailing_stop.tone;
           const cls = tone === 'up' ? 'pos' : (tone === 'down' ? 'neg' : 'warn');
           tfBadge = `<strong class="${cls}">${fmt.escape(tf.step5_trailing_stop.holding_status || '')}</strong>`;
        }
        
        const volRatio = ind.volume_ratio != null ? ind.volume_ratio + '×' : '—';
        const volVal = data.candles && data.candles.length ? data.candles[data.candles.length-1].v : null;
        const volText = volVal ? fmt.vol(volVal) : '—';
        
        let srHtml = '—';
        if (data.supports && data.supports.length) {
            srHtml = 'HT: ' + fmt.price(data.supports[0].price);
        }
        if (data.resistances && data.resistances.length) {
            if (srHtml === '—') srHtml = '';
            else srHtml += ' | ';
            srHtml += 'KC: ' + fmt.price(data.resistances[0].price);
        }

        cards.push(`
          <div class="card" style="padding:16px;">
            <div class="flex-between" style="margin-bottom:12px;">
              <h3 style="margin:0;font-size:17px;"><a href="/phan-tich?symbol=${sym}" style="color:var(--text);text-decoration:none;">${sym}</a></h3>
              <span class="chip ${fmt.tone(data.change_pct)}">${fmt.price(data.price)} (${fmt.pct(data.change_pct)})</span>
            </div>
            <div class="kv-list mt-8">
              <div class="kv-row"><span class="k">Tín hiệu</span><span class="v">${App.signalBadge(s)}</span></div>
              <div class="kv-row"><span class="k">Ngưỡng kỹ thuật</span><span class="v">${srHtml}</span></div>
              <div class="kv-row"><span class="k">Trend Following</span><span class="v">${tfBadge}</span></div>
              <div class="kv-row"><span class="k">Khối lượng</span><span class="v">${volText} (${volRatio} TB20)</span></div>
            </div>
          </div>
        `);
      } catch (e) {
        cards.push(`
          <div class="card" style="padding:16px;">
            <div class="flex-between" style="margin-bottom:12px;">
              <h3 style="margin:0;font-size:17px;">${sym}</h3>
            </div>
            <div class="muted small">Lỗi tải dữ liệu: ${fmt.escape(e.message)}</div>
          </div>
        `);
      }
    }
    grid.innerHTML = cards.join('');
  }

  document.addEventListener('DOMContentLoaded', () => {"""

if 'loadMarketAnalysis' not in content:
    content = content.replace("document.addEventListener('DOMContentLoaded', () => {", new_func)
    content = content.replace('loadRecent();\n    loadTopSignals();', 'loadRecent();\n    loadTopSignals();\n    loadMarketAnalysis();')
    if 'loadMarketAnalysis();' not in content:
        content = content.replace('loadRecent();\r\n    loadTopSignals();', 'loadRecent();\r\n    loadTopSignals();\r\n    loadMarketAnalysis();')
        
    with open('fintech/static/js/dashboard.js', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Injected loadMarketAnalysis in dashboard.js')
else:
    print('loadMarketAnalysis already exists')

