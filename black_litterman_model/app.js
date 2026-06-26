// ══════════════════════════════════════════════════════════════
// app.js — UI state, page navigation and wiring for the BL optimizer
// ══════════════════════════════════════════════════════════════

// ══════════════════════════════════════════════════════════════
// TICKER NAME CACHE — populated dynamically (no hardcoding)
//   • from /api/search when user picks a ticker from dropdown
//   • from /api/data meta when market data is fetched
// ══════════════════════════════════════════════════════════════
const tickerNameCache = new Map();  // 'AAPL' → 'Apple Inc.'

// ══════════════════════════════════════════════════════════════
// BACKEND API BASE — all /api/* calls go to FastAPI on :8000
// ══════════════════════════════════════════════════════════════
const API_BASE = 'http://localhost:8000';

// ══════════════════════════════════════════════════════════════
// PORTS — stored in MongoDB via backend API
// ══════════════════════════════════════════════════════════════
let ports = [];  // populated async by fetchPorts()

async function fetchPorts() {
  try {
    const res = await fetch(`${API_BASE}/api/ports`);
    const json = await res.json();
    // map snake_case last_run → camelCase lastRun for frontend
    ports = (json.data || []).map(p => ({ ...p, lastRun: p.last_run ?? null }));
  } catch (e) {
    console.warn('fetchPorts failed — is backend running on :8000?', e);
    ports = [];
  }
  renderPortChips();
}

const CONFIDENCE = {
  'สูงมาก':   0.0002,
  'สูง':      0.0005,
  'ปานกลาง':  0.0010,
  'ต่ำ':      0.0020,
  'ต่ำมาก':    0.0050,
};

// ── Risk / constraint config ───────────────────────────────────
const rf   = () => +rfEl.value / 100;
const minW = () => +minwEl.value / 100;
const maxW = () => +maxwEl.value / 100;
const Q_FLOOR    = 0.03;   // auto-view expected return floor (#3)
const Q_CAP      = 0.15;   // auto-view expected return cap   (#3)

// Clamp an auto-generated view's Q into [Q_FLOOR, Q_CAP], keeping its sign.
function capQ(x) {
  const c = Math.max(Q_FLOOR, Math.min(Q_CAP, Math.abs(x)));
  return round(x < 0 ? -c : c);
}

// ── Global state ──────────────────────────────────────────────
const state = {
  tickers: ['AAPL', 'MSFT', 'GOOGL', 'NVDA'],
  market: null,        // { dates, prices, marketCap, meta, wMkt, sigma, R, signals }
  views: [],           // [{ id, enabled, type, picks:{T:val}, q, omega }]
  results: null,
  nextViewId: 1,
};

const $  = sel => document.querySelector(sel);
const $$ = sel => [...document.querySelectorAll(sel)];

// ── Navigation ────────────────────────────────────────────────
function goto(page) {
  $$('.tab').forEach(t => t.classList.toggle('active', t.dataset.page === page));
  $$('.page').forEach(p => p.classList.toggle('active', p.id === `page-${page}`));
}
$$('.tab').forEach(t => t.addEventListener('click', () => goto(t.dataset.page)));

// ══════════════════════════════════════════════════════════════
// TICKER CHIPS
// ══════════════════════════════════════════════════════════════
function renderChips() {
  const wrap = $('#ticker-chips');
  wrap.innerHTML = '';
  state.tickers.forEach(t => {
    const name = tickerNameCache.get(t) || '';
    const chip = document.createElement('span');
    chip.className = 'chip';
    chip.innerHTML = `<b>${t}</b>${name ? `<span class="chip-name">${name}</span>` : ''} <button title="ลบ">×</button>`;
    chip.querySelector('button').addEventListener('click', () => {
      state.tickers = state.tickers.filter(x => x !== t);
      renderChips();
    });
    wrap.appendChild(chip);
  });
}

function addTicker(raw) {
  const t = (raw || '').trim().toUpperCase();
  if (!t) return;
  if (!state.tickers.includes(t)) state.tickers.push(t);
  renderChips();
}

// ══════════════════════════════════════════════════════════════
// AUTOCOMPLETE
// ══════════════════════════════════════════════════════════════
const tickerInput = $('#ticker-input');
const suggestList = $('#ticker-suggest');
let acIndex = -1;   // keyboard-nav index
let searchTimer = null;  // debounce handle for live search

// ── Live ticker search (debounced → /api/search) ──────────────
tickerInput.addEventListener('input', () => {
  const q = tickerInput.value.trim();
  clearTimeout(searchTimer);
  if (!q) { suggestList.hidden = true; return; }

  // Show loading placeholder immediately so the user sees feedback
  suggestList.innerHTML = '<li class="suggest-item suggest-loading">🔍 กำลังค้นหา…</li>';
  suggestList.hidden = false;

  searchTimer = setTimeout(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/search?q=${encodeURIComponent(q)}`);
      const json = await res.json();
      renderAPIResults(json.data?.results || [], q);
    } catch {
      renderOfflineFallback();
    }
  }, 250);
});

// Render results from /api/search
function renderAPIResults(results, rawQuery) {
  suggestList.innerHTML = '';
  acIndex = -1;
  const upper = rawQuery.trim().toUpperCase();

  if (!results.length) {
    // Nothing found — offer to add as custom ticker
    const li = document.createElement('li');
    li.className = 'suggest-item suggest-custom';
    li.innerHTML = `<b>${upper}</b><span>➕ เพิ่ม custom ticker</span>`;
    li.addEventListener('mousedown', e => { e.preventDefault(); selectSuggestion(upper); });
    suggestList.appendChild(li);
    suggestList.hidden = false;
    return;
  }

  results.forEach(({ symbol, name, exchange, type }) => {
    const li = document.createElement('li');
    li.className = 'suggest-item';
    li.dataset.name = name;
    const meta = [exchange, type].filter(Boolean).join(' · ');
    li.innerHTML = `<b>${symbol}</b><span>${name}${meta ? '  <em>' + meta + '</em>' : ''}</span>`;
    li.addEventListener('mousedown', e => { e.preventDefault(); selectSuggestion(symbol, name); });
    suggestList.appendChild(li);
  });
  suggestList.hidden = false;
}

// Fallback when backend is unreachable — offer custom ticker only
function renderOfflineFallback() {
  const raw = tickerInput.value.trim().toUpperCase();
  suggestList.innerHTML = '';
  acIndex = -1;
  if (!raw) { suggestList.hidden = true; return; }
  const li = document.createElement('li');
  li.className = 'suggest-item suggest-custom';
  li.innerHTML = `<b>${raw}</b><span>➕ เพิ่ม custom ticker (backend offline)</span>`;
  li.addEventListener('mousedown', e => { e.preventDefault(); selectSuggestion(raw); });
  suggestList.appendChild(li);
  suggestList.hidden = false;
}

function selectSuggestion(sym, name = '') {
  if (name) tickerNameCache.set(sym, name);
  addTicker(sym);
  tickerInput.value = '';
  suggestList.hidden = true;
  acIndex = -1;
  clearTimeout(searchTimer);
}

function highlightItem(idx) {
  const items = suggestList.querySelectorAll('.suggest-item');
  items.forEach((li, i) => li.classList.toggle('active', i === idx));
}

tickerInput.addEventListener('keydown', e => {
  const items = suggestList.querySelectorAll('.suggest-item');
  if (e.key === 'ArrowDown') {
    e.preventDefault();
    acIndex = Math.min(acIndex + 1, items.length - 1);
    highlightItem(acIndex);
  } else if (e.key === 'ArrowUp') {
    e.preventDefault();
    acIndex = Math.max(acIndex - 1, -1);
    highlightItem(acIndex);
  } else if (e.key === 'Enter') {
    e.preventDefault();
    if (acIndex >= 0 && items[acIndex]) {
      const sym = items[acIndex].querySelector('b').textContent;
      const name = items[acIndex].dataset.name || '';
      selectSuggestion(sym, name);
    } else {
      addTicker(tickerInput.value);
      tickerInput.value = '';
      suggestList.hidden = true;
    }
  } else if (e.key === 'Escape') {
    suggestList.hidden = true;
  }
});

tickerInput.addEventListener('blur', () => {
  setTimeout(() => { suggestList.hidden = true; }, 120);
});

$('#add-ticker').addEventListener('click', () => {
  addTicker(tickerInput.value);
  tickerInput.value = '';
  suggestList.hidden = true;
});

// ══════════════════════════════════════════════════════════════
// PORTS — port-chip row + modals
// ══════════════════════════════════════════════════════════════
function renderPortChips() {
  const row = $('#port-chips-row');
  row.innerHTML = '';
  if (!ports.length) {
    row.innerHTML = '<span class="muted" style="font-size:12px;padding:4px 2px">ยังไม่มี Port — กด "Save as Port" เพื่อสร้าง</span>';
    return;
  }
  ports.forEach(p => {
    const wrap = document.createElement('div');
    wrap.className = 'chip-btn port-chip';
    wrap.title = p.tickers.join(', ');

    let metricsHtml = '';
    if (p.lastRun) {
      const { expReturn, sharpe } = p.lastRun.metrics;
      metricsHtml = `<span class="port-chip-metrics">${pct(expReturn)} · SR ${sharpe.toFixed(2)}</span>`;
    }

    wrap.innerHTML = `
      <div class="port-chip-top">
        <span class="port-chip-name">${p.name}</span>
        <span class="port-chip-count">${p.tickers.length}</span>
        <div class="port-chip-actions">
          <button class="port-chip-rename icon-btn" title="เปลี่ยนชื่อ">✏️</button>
          <button class="port-chip-del icon-btn" title="ลบ Port">✕</button>
        </div>
      </div>
      ${metricsHtml}`;

    wrap.querySelector('.port-chip-top').addEventListener('click', e => {
      if (e.target.closest('.port-chip-actions')) return;
      state.tickers = [...p.tickers];
      renderChips();
      wrap.classList.add('port-chip-active');
      setTimeout(() => wrap.classList.remove('port-chip-active'), 600);
    });

    wrap.querySelector('.port-chip-rename').addEventListener('click', async e => {
      e.stopPropagation();
      const newName = prompt(`เปลี่ยนชื่อ Port "${p.name}":`, p.name);
      if (!newName || !newName.trim() || newName.trim() === p.name) return;
      await fetch(`${API_BASE}/api/ports/${p.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newName.trim() }),
      });
      await fetchPorts();
    });

    wrap.querySelector('.port-chip-del').addEventListener('click', async e => {
      e.stopPropagation();
      if (!confirm(`ลบ Port "${p.name}"?`)) return;
      await fetch(`${API_BASE}/api/ports/${p.id}`, { method: 'DELETE' });
      await fetchPorts();
    });

    row.appendChild(wrap);
  });
}

// ── Save as Port ──────────────────────────────────────────────
$('#save-as-port').addEventListener('click', async () => {
  if (!state.tickers.length) { alert('เพิ่มหุ้นก่อนบันทึก'); return; }
  const name = prompt(`บันทึก Port ใหม่\n\nหุ้น: ${state.tickers.join(' · ')}\n\nใส่ชื่อ Port:`);
  if (!name || !name.trim()) return;
  const trimmed = name.trim();
  const existing = ports.find(p => p.name.toLowerCase() === trimmed.toLowerCase());
  try {
    if (existing) {
      if (!confirm(`Port "${trimmed}" มีอยู่แล้ว — อัปเดต tickers?`)) return;
      await fetch(`${API_BASE}/api/ports/${existing.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tickers: [...state.tickers] }),
      });
    } else {
      await fetch(`${API_BASE}/api/ports`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: trimmed, tickers: [...state.tickers] }),
      });
    }
    await fetchPorts();
  } catch (e) {
    alert('บันทึกไม่สำเร็จ: ' + e.message);
  }
});


// ── Sliders ───────────────────────────────────────────────────
const deltaEl = $('#delta'), tauEl = $('#tau'), periodEl = $('#period'), rfEl = $('#rf');
const minwEl  = $('#minw'),  maxwEl  = $('#maxw');
deltaEl.addEventListener('input',  () => $('#delta-val').textContent  = (+deltaEl.value).toFixed(1));
tauEl.addEventListener('input',    () => $('#tau-val').textContent    = (+tauEl.value).toFixed(2));
periodEl.addEventListener('input', () => $('#period-val').textContent = `${periodEl.value} ปี`);
rfEl.addEventListener('input',     () => $('#rf-val').textContent     = (+rfEl.value).toFixed(2) + '%');
minwEl.addEventListener('input',   () => { $('#minw-val').textContent = minwEl.value + '%'; validateMinMax(); });
maxwEl.addEventListener('input',   () => { $('#maxw-val').textContent = maxwEl.value + '%'; validateMinMax(); });

function validateMinMax() {
  // Ensure min < max; clamp if user drags them past each other
  if (+minwEl.value >= +maxwEl.value) {
    minwEl.value = Math.max(0, +maxwEl.value - 5);
    $('#minw-val').textContent = minwEl.value + '%';
  }
}

// ── Fetch market data ─────────────────────────────────────────
function setStatus(msg, cls = '') { const el = $('#fetch-status'); el.textContent = msg; el.className = `status ${cls}`; }

$('#fetch-data').addEventListener('click', async () => {
  if (!state.tickers.length) { setStatus('เพิ่มหุ้นอย่างน้อย 1 ตัวก่อน', 'err'); return; }
  const btn = $('#fetch-data');
  btn.disabled = true;
  setStatus('กำลังดึงข้อมูลจาก Yahoo Finance…', 'load');
  try {
    const period = `${periodEl.value}y`;
    const url = `${API_BASE}/api/data?tickers=${encodeURIComponent(state.tickers.join(','))}&period=${period}`;
    const res = await fetch(url);
    const json = await res.json();
    if (!json.ok) throw new Error(json.error || 'fetch failed');
    buildMarket(json.data);
    const got = Object.keys(state.market.prices).length;
    const errs = Object.keys(json.data.errors || {});
    setStatus(`✅ ได้ข้อมูล ${got} ตัว` + (errs.length ? ` · ข้าม: ${errs.join(', ')}` : ''), 'ok');
    renderPreview();
  } catch (e) {
    setStatus(`❌ ${e.message}`, 'err');
  } finally {
    btn.disabled = false;
  }
});

// Process raw backend payload into aligned matrices + signals.
function buildMarket(data) {
  const aligned = Stats.alignPrices(data.prices);
  const tickers = Object.keys(aligned.prices);          // only tickers with data
  state.tickers = tickers;                              // drop failed ones
  renderChips();

  const R      = Stats.returnsMatrix(aligned.prices, tickers);
  const sigma  = Stats.covariance(R);
  const vol    = tickers.map((_, j) => Stats.annualVol(R, j));
  const wMkt    = Stats.marketWeights(data.marketCap, tickers);
  const wEqual  = Stats.equalWeights(tickers.length);
  const wInvVol = Stats.inverseVolWeights(vol);

  // Populate name cache from yfinance meta (no hardcoding needed)
  for (const [sym, info] of Object.entries(data.meta || {})) {
    if (info.name) tickerNameCache.set(sym, info.name);
  }
  renderChips();  // re-render chips now that names are available

  state.market = {
    tickers,
    dates: aligned.dates,
    prices: aligned.prices,
    marketCap: data.marketCap,
    meta: data.meta || {},
    R, sigma, wMkt, wEqual, wInvVol,
    vol,
    signals: {
      momentum: Stats.momentum(aligned.prices, tickers),
      zscore:   Stats.zScore(aligned.prices, tickers),
      rs:       Stats.relativeStrength(aligned.prices, tickers),
    },
  };
}

function renderPreview() {
  const m = state.market;
  const tbody = $('#preview-table tbody');
  tbody.innerHTML = '';
  m.tickers.forEach((t, i) => {
    const tr = document.createElement('tr');
    const cap = m.marketCap[t];
    tr.innerHTML = `
      <td><b>${t}</b></td>
      <td class="muted" style="text-align:left">${(m.meta[t]?.name || '').slice(0, 28)}</td>
      <td class="mono">${fmtCap(cap)}</td>
      <td class="mono">${pct(m.wMkt[i])}</td>
      <td class="mono">${pct(m.vol[i])}</td>
      <td class="mono ${m.signals.momentum[i] >= 0 ? 'pos' : 'neg'}">${pct(m.signals.momentum[i])}</td>
      <td class="pos">OK</td>`;
    tbody.appendChild(tr);
  });
}

// ══════════════════════════════════════════════════════════════
// VIEWS
// ══════════════════════════════════════════════════════════════
function blankView() {
  const picks = {};
  state.tickers.forEach(t => picks[t] = 0);
  return { id: state.nextViewId++, enabled: true, type: 'absolute', picks, q: 0.05, omega: 0.0005 };
}

$('#add-view').addEventListener('click', () => {
  if (!state.tickers.length) { alert('เพิ่มหุ้นในหน้า Setup ก่อน'); return; }
  state.views.push(blankView());
  renderViews();
});

function renderViews() {
  const list = $('#views-list');
  list.innerHTML = '';
  if (!state.views.length) {
    list.innerHTML = '<p class="muted" id="no-views-msg">ยังไม่มี view — กด "เพิ่ม View" หรือ "Generate Auto Views"</p>';
    renderViewSummary();
    return;
  }
  state.views.forEach((v, idx) => list.appendChild(viewCard(v, idx)));
  renderViewSummary();
}

function viewCard(v, idx) {
  const card = document.createElement('div');
  card.className = 'view-card' + (v.enabled ? '' : ' disabled');

  const picksHtml = state.tickers.map(t => `
    <div class="pick-cell">
      <span>${t}</span>
      <input type="number" step="0.5" data-pick="${t}" value="${v.picks[t] ?? 0}" />
    </div>`).join('');

  const confOptions = Object.entries(CONFIDENCE).map(([k, val]) =>
    `<option value="${val}" ${Math.abs(val - v.omega) < 1e-9 ? 'selected' : ''}>${k} (${val})</option>`).join('');

  card.innerHTML = `
    <div class="view-card-head">
      <span class="vtitle">View #${idx + 1}</span>
      <div class="vactions">
        <label class="chk"><input type="checkbox" data-enabled ${v.enabled ? 'checked' : ''} /> เปิด</label>
        <button class="icon-btn" data-del title="ลบ">🗑</button>
      </div>
    </div>
    <div class="view-type">
      <label><input type="radio" name="vt-${v.id}" value="absolute" ${v.type === 'absolute' ? 'checked' : ''}/> Absolute</label>
      <label><input type="radio" name="vt-${v.id}" value="relative" ${v.type === 'relative' ? 'checked' : ''}/> Relative</label>
    </div>
    <div class="pick-grid">${picksHtml}</div>
    <div class="view-row">
      <div class="field">
        <label>Q — Expected return (%)</label>
        <input type="number" step="0.5" data-q value="${(v.q * 100).toFixed(2)}" />
      </div>
      <div class="field">
        <label>Ω — Confidence</label>
        <select data-omega>${confOptions}</select>
      </div>
    </div>`;

  // wiring
  card.querySelector('[data-enabled]').addEventListener('change', e => { v.enabled = e.target.checked; renderViews(); });
  card.querySelector('[data-del]').addEventListener('click', () => { state.views = state.views.filter(x => x.id !== v.id); renderViews(); });
  card.querySelectorAll(`input[name="vt-${v.id}"]`).forEach(r =>
    r.addEventListener('change', e => { v.type = e.target.value; }));
  card.querySelectorAll('[data-pick]').forEach(inp =>
    inp.addEventListener('input', e => { v.picks[e.target.dataset.pick] = parseFloat(e.target.value) || 0; renderViewSummary(); }));
  card.querySelector('[data-q]').addEventListener('input', e => { v.q = (parseFloat(e.target.value) || 0) / 100; renderViewSummary(); });
  card.querySelector('[data-omega]').addEventListener('change', e => { v.omega = parseFloat(e.target.value); renderViewSummary(); });

  return card;
}

function renderViewSummary() {
  const tbody = $('#view-summary tbody');
  const active = state.views.filter(v => v.enabled);
  if (!active.length) { tbody.innerHTML = '<tr><td colspan="6" class="muted">ยังไม่มี view</td></tr>'; return; }
  tbody.innerHTML = '';
  active.forEach((v, i) => {
    const picks = Object.entries(v.picks).filter(([, x]) => x !== 0);
    const up = picks.filter(([, x]) => x > 0).map(([t]) => t).join(', ') || '—';
    const down = picks.filter(([, x]) => x < 0).map(([t]) => t).join(', ') || '—';
    const confName = Object.entries(CONFIDENCE).find(([, val]) => Math.abs(val - v.omega) < 1e-9)?.[0] || 'custom';
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${i + 1}</td>
      <td style="text-align:left">${v.type === 'absolute' ? 'Absolute' : 'Relative'}</td>
      <td style="text-align:left">${picks.map(([t, x]) => `${t}:${x > 0 ? '+' : ''}${x}`).join('  ')}</td>
      <td class="mono">${pct(v.q)}</td>
      <td>${confName}</td>
      <td style="text-align:left"><span class="pos">▲ ${up}</span> &nbsp; <span class="neg">▼ ${down}</span></td>`;
    tbody.appendChild(tr);
  });
}

// ── Auto signal generator ─────────────────────────────────────
$('#gen-auto').addEventListener('click', () => {
  if (!state.market) { alert('ดึงข้อมูลตลาดในหน้า Setup ก่อน'); return; }
  const m = state.market, T = m.tickers;
  const generated = [];

  // Momentum → absolute views: tilt prior return by momentum strength.
  if ($('#sig-mom').checked) {
    T.forEach((t, i) => {
      const sig = m.signals.momentum[i];
      if (Math.abs(sig) < 0.02) return;               // ignore weak signals
      const picks = {}; T.forEach(x => picks[x] = 0); picks[t] = 1;
      // anchor on the implied prior, nudged by the momentum signal
      const pi = BL.impliedReturns(+deltaEl.value, m.sigma, m.wMkt)[i];
      generated.push({ id: state.nextViewId++, enabled: true, type: 'absolute',
        picks, q: capQ(pi + 0.5 * sig), omega: confFromStrength(Math.abs(sig)) });
    });
  }

  // Relative strength → one relative view: best vs worst.
  if ($('#sig-rs').checked && T.length >= 2) {
    const rs = m.signals.rs;
    const best = rs.indexOf(Math.max(...rs));
    const worst = rs.indexOf(Math.min(...rs));
    if (best !== worst) {
      const picks = {}; T.forEach(x => picks[x] = 0);
      picks[T[best]] = 1; picks[T[worst]] = -1;
      generated.push({ id: state.nextViewId++, enabled: true, type: 'relative',
        picks, q: capQ(rs[best] - rs[worst]), omega: 0.0010 });
    }
  }

  // Mean reversion → relative view: most oversold vs most overbought.
  if ($('#sig-rev').checked && T.length >= 2) {
    const z = m.signals.zscore;
    const cheap = z.indexOf(Math.min(...z));    // low z = below mean = upside
    const rich = z.indexOf(Math.max(...z));
    if (cheap !== rich && (z[rich] - z[cheap]) > 0.5) {
      const picks = {}; T.forEach(x => picks[x] = 0);
      picks[T[cheap]] = 1; picks[T[rich]] = -1;
      generated.push({ id: state.nextViewId++, enabled: true, type: 'relative',
        picks, q: capQ(0.01 * (z[rich] - z[cheap])), omega: 0.0020 });
    }
  }

  if (!generated.length) { alert('signal อ่อนเกินไป — ไม่มี view ที่สร้างได้'); return; }
  state.views.push(...generated);
  renderViews();
});

function confFromStrength(s) {
  if (s > 0.25) return 0.0005;
  if (s > 0.12) return 0.0010;
  return 0.0020;
}

// ══════════════════════════════════════════════════════════════
// RUN BLACK-LITTERMAN
// ══════════════════════════════════════════════════════════════
$('#run-bl').addEventListener('click', () => {
  if (!state.market) { alert('ดึงข้อมูลตลาดในหน้า Setup ก่อน'); goto('setup'); return; }
  const m = state.market, T = m.tickers;
  const delta = +deltaEl.value, tau = +tauEl.value;

  // Validate views before sending them to the engine: drop any with an
  // all-zero pick vector or a ~zero Q — they add no information. (#7)
  const active = state.views.filter(v =>
    v.enabled &&
    Object.values(v.picks).some(x => x !== 0) &&
    Math.abs(v.q) > 0.001);

  const skipped = state.views.filter(v => v.enabled).length - active.length;

  let P = null, Q = null, omega = null;
  if (active.length) {
    P = active.map(v => T.map(t => v.picks[t] || 0));
    Q = active.map(v => v.q);
    omega = active.map(v => v.omega);
  }

  let out;
  try {
    out = BL.compute({ delta, tau, sigma: m.sigma, wMkt: m.wMkt, P, Q, omega });
  } catch (e) {
    alert('คำนวณไม่สำเร็จ: ' + e.message + '\n(อาจเป็นเพราะ covariance matrix singular)');
    return;
  }

  // Unconstrained weights → tradeable weights via long-only + min/max. (#1, #2)
  const wRaw = BL.optimalWeights(delta, out.sigmaBL, out.muBL);
  const wStar = BL.constrainWeights(wRaw, { longOnly: true, minW: minW(), maxW: maxW() });

  state.results = {
    tickers: T,
    wMkt: m.wMkt, wStar, wRaw,
    pi: out.pi, muBL: out.muBL,
    sigma: m.sigma, sigmaBL: out.sigmaBL,
    skipped,
    metrics: {
      expReturn: BL.portfolioReturn(wStar, out.muBL),
      vol: BL.portfolioVol(wStar, m.sigma),
      sharpe: BL.sharpe(wStar, out.muBL, m.sigma, rf()),
      te: BL.trackingError(wStar, m.wMkt, m.sigma),
      leverage: BL.leverage(wRaw),                              // (#9)
    },
  };
  renderResults();
  goto('results');
});

function renderResults() {
  const r = state.results;
  $('#results-empty').style.display = 'none';
  $('#results-body').style.display = 'block';

  // metrics — colour-coded by threshold (#6 TE, #8 return)
  const { expReturn: er, vol, sharpe: sh, te, leverage: lev } = r.metrics;
  const teCls = te > 0.10 ? 'neg' : te > 0.05 ? 'warn' : 'pos';
  const teTag = te > 0.10 ? ' ⚠' : te > 0.05 ? ' •' : ' ✓';
  const erCls = er > 0.30 ? 'neg' : '';
  $('#metrics-row').innerHTML = [
    ['Expected Return', pct(er), erCls],
    ['Volatility', pct(vol), ''],
    [`Sharpe Ratio <span class="m-sub">rf ${pct(rf())}</span>`, sh.toFixed(2), ''],
    [`Tracking Error<span class="m-sub">vs market${teTag}</span>`, pct(te), teCls],
  ].map(([l, v, c]) => `<div class="metric"><div class="m-label">${l}</div><div class="m-value ${c}">${v}</div></div>`).join('');

  // warning banners (#6, #8, #9, #7)
  const warns = [];
  if (te > 0.10) warns.push(`⚠ Tracking Error ${pct(te)} สูงเกินมาตรฐาน Active Fund (ปกติ 2–8%)`);
  else if (te > 0.05) warns.push(`ระวัง: Tracking Error ${pct(te)} ค่อนข้างสูง`);
  if (er > 0.30) warns.push(`⚠ Expected Return ${pct(er)} สูงผิดปกติ — ตรวจสอบ Views`);
  if (lev > 1.2) warns.push(`⚠ Leverage ${lev.toFixed(2)}× — ก่อน constraint โมเดลต้องการ short positions มาก (ถูก long-only ปรับแล้ว)`);
  if (r.skipped > 0) warns.push(`ℹ ข้าม ${r.skipped} view ที่ไม่มีน้ำหนัก (pick = 0 หรือ Q ≈ 0)`);
  $('#results-warnings').innerHTML = warns.map(w =>
    `<div class="warn-banner${w.startsWith('⚠') ? ' crit' : ''}">${w}</div>`).join('');

  // weight table
  const wtb = $('#weight-table tbody'); wtb.innerHTML = '';
  r.tickers.forEach((t, i) => {
    const d = r.wStar[i] - r.wMkt[i];
    wtb.innerHTML += `<tr><td><b>${t}</b></td><td class="mono">${pct(r.wMkt[i])}</td>
      <td class="mono">${pct(r.wStar[i])}</td><td class="mono ${cls(d)}">${signed(d)} ${arrow(d)}</td></tr>`;
  });
  renderWeightChart(r);

  // return table
  const rtb = $('#return-table tbody'); rtb.innerHTML = '';
  r.tickers.forEach((t, i) => {
    const d = r.muBL[i] - r.pi[i];
    rtb.innerHTML += `<tr><td><b>${t}</b></td><td class="mono">${pct(r.pi[i])}</td>
      <td class="mono">${pct(r.muBL[i])}</td><td class="mono ${cls(d)}">${signed(d)}</td></tr>`;
  });

  renderFrontier(r);
}

function renderWeightChart(r) {
  const maxW = Math.max(...r.wMkt, ...r.wStar, 0.01);
  const rows = r.tickers.map((t, i) => `
    <div class="bar-row">
      <span>${t}</span>
      <div class="bar-track">
        <div class="bar-seg bar-mkt" style="width:${(r.wMkt[i] / maxW * 100).toFixed(1)}%"></div>
        <div class="bar-seg bar-bl"  style="width:${(Math.max(r.wStar[i], 0) / maxW * 100).toFixed(1)}%; opacity:.85"></div>
      </div>
    </div>`).join('');
  $('#weight-chart').innerHTML = rows +
    `<div class="bar-legend"><span><i class="dot dot-mkt"></i>w_mkt</span><span><i class="dot dot-bl"></i>w* (BL)</span></div>`;
}

// ── Efficient frontier (canvas scatter) ──────────────────────
function renderFrontier(r) {
  const canvas = $('#frontier-canvas');
  const ctx = canvas.getContext('2d');
  const W = canvas.width, H = canvas.height;
  const pad = { l: 60, r: 20, t: 20, b: 45 };
  ctx.clearRect(0, 0, W, H);

  // Use historical sigma (same as metrics card) so chart vol matches displayed numbers.
  const cloud = BL.randomPortfolios(r.muBL, r.sigma, rf(), 1800);
  const blPt = { vol: BL.portfolioVol(r.wStar, r.sigma), ret: BL.portfolioReturn(r.wStar, r.muBL) };
  const mkPt = { vol: BL.portfolioVol(r.wMkt, r.sigma), ret: BL.portfolioReturn(r.wMkt, r.muBL) };
  const maxSharpe = cloud.reduce((a, b) => b.sharpe > a.sharpe ? b : a, cloud[0]);

  const all = [...cloud, blPt, mkPt];
  const xs = all.map(p => p.vol), ys = all.map(p => p.ret);
  const xMin = Math.min(...xs) * 0.95, xMax = Math.max(...xs) * 1.05;
  const yMin = Math.min(...ys, 0) * 1.05, yMax = Math.max(...ys) * 1.1;

  const sx = v => pad.l + (v - xMin) / (xMax - xMin) * (W - pad.l - pad.r);
  const sy = v => H - pad.b - (v - yMin) / (yMax - yMin) * (H - pad.t - pad.b);

  // axes + grid
  ctx.strokeStyle = '#2a3340'; ctx.fillStyle = '#8b97a7'; ctx.font = '11px sans-serif';
  ctx.lineWidth = 1;
  for (let i = 0; i <= 5; i++) {
    const gy = pad.t + i / 5 * (H - pad.t - pad.b);
    ctx.beginPath(); ctx.moveTo(pad.l, gy); ctx.lineTo(W - pad.r, gy); ctx.stroke();
    const val = yMax - i / 5 * (yMax - yMin);
    ctx.fillText((val * 100).toFixed(0) + '%', 8, gy + 4);
  }
  for (let i = 0; i <= 5; i++) {
    const gx = pad.l + i / 5 * (W - pad.l - pad.r);
    const val = xMin + i / 5 * (xMax - xMin);
    ctx.fillText((val * 100).toFixed(0) + '%', gx - 8, H - pad.b + 18);
  }
  ctx.fillText('Volatility →', W / 2 - 30, H - 8);
  ctx.save(); ctx.translate(16, H / 2 + 30); ctx.rotate(-Math.PI / 2); ctx.fillText('Expected Return →', 0, 0); ctx.restore();

  // cloud
  cloud.forEach(p => {
    ctx.fillStyle = `rgba(79,156,255,${0.1 + p.sharpe * 0.12})`;
    ctx.beginPath(); ctx.arc(sx(p.vol), sy(p.ret), 2.4, 0, 2 * Math.PI); ctx.fill();
  });

  const mark = (p, color, label, rad = 7) => {
    ctx.fillStyle = color;
    ctx.beginPath(); ctx.arc(sx(p.vol), sy(p.ret), rad, 0, 2 * Math.PI); ctx.fill();
    ctx.strokeStyle = '#0e1117'; ctx.lineWidth = 2; ctx.stroke();
    ctx.fillStyle = '#e6edf3'; ctx.font = 'bold 12px sans-serif';
    ctx.fillText(label, sx(p.vol) + 10, sy(p.ret) + 4);
  };
  mark(maxSharpe, '#2ecc71', 'Max Sharpe');
  mark(mkPt, '#f5c451', 'Market');
  mark(blPt, '#4f9cff', 'BL Optimal');
}

// ── Export ────────────────────────────────────────────────────
$('#export-csv').addEventListener('click', () => {
  const r = state.results; if (!r) return;
  let csv = 'Ticker,w_mkt,w_BL,delta_weight,Pi_prior,mu_BL\n';
  r.tickers.forEach((t, i) => {
    csv += `${t},${r.wMkt[i].toFixed(4)},${r.wStar[i].toFixed(4)},${(r.wStar[i] - r.wMkt[i]).toFixed(4)},${r.pi[i].toFixed(4)},${r.muBL[i].toFixed(4)}\n`;
  });
  csv += `\nExpected Return,${r.metrics.expReturn.toFixed(4)}\nVolatility,${r.metrics.vol.toFixed(4)}\nSharpe,${r.metrics.sharpe.toFixed(4)}\nTracking Error,${r.metrics.te.toFixed(4)}\n`;
  const blob = new Blob([csv], { type: 'text/csv' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob); a.download = 'bl_weights.csv'; a.click();
});

$('#copy-summary').addEventListener('click', () => {
  const r = state.results; if (!r) return;
  let txt = 'BLACK-LITTERMAN OPTIMAL PORTFOLIO\n' + '='.repeat(40) + '\n';
  r.tickers.forEach((t, i) =>
    txt += `${t.padEnd(10)} ${pct(r.wMkt[i]).padStart(8)} → ${pct(r.wStar[i]).padStart(8)}  (${signed(r.wStar[i] - r.wMkt[i])})\n`);
  txt += '-'.repeat(40) + `\nExp Return: ${pct(r.metrics.expReturn)}  Vol: ${pct(r.metrics.vol)}  Sharpe: ${r.metrics.sharpe.toFixed(2)}\n`;
  navigator.clipboard.writeText(txt).then(() => {
    const b = $('#copy-summary'); const old = b.textContent; b.textContent = '✅ Copied!';
    setTimeout(() => b.textContent = old, 1500);
  });
});

// ── Save Results to Port ──────────────────────────────────────
$('#save-results-port').addEventListener('click', () => {
  if (!state.results) { alert('คำนวณ BL ก่อนแล้วค่อยบันทึก'); return; }
  renderSaveResultsModal();
  $('#save-results-modal').hidden = false;
  setTimeout(() => $('#save-results-modal').querySelector('input')?.focus(), 50);
});

function closeSaveResultsModal() { $('#save-results-modal').hidden = true; }
$('#close-save-results-modal').addEventListener('click', closeSaveResultsModal);
$('#save-results-modal').addEventListener('click', e => {
  if (e.target === $('#save-results-modal')) closeSaveResultsModal();
});

function renderSaveResultsModal() {
  const r = state.results;
  const body = $('#save-results-modal-body');
  body.innerHTML = '';

  // Existing ports
  if (ports.length) {
    const title = document.createElement('p');
    title.className = 'modal-section-label';
    title.textContent = 'บันทึกลง Port ที่มีอยู่';
    body.appendChild(title);

    ports.forEach((p, idx) => {
      const tickersMatch = JSON.stringify([...r.tickers].sort()) === JSON.stringify([...p.tickers].sort());
      const row = document.createElement('div');
      row.className = 'sri-row' + (tickersMatch ? ' sri-match' : '');
      row.innerHTML = `
        <div class="sri-info">
          <span class="sri-name">${p.name}</span>
          <span class="sri-tickers">${p.tickers.join(' · ')}</span>
          ${tickersMatch ? '<span class="sri-badge">✓ tickers ตรงกัน</span>' : ''}
        </div>
        <button class="btn btn-sm" data-idx="${idx}">บันทึก</button>`;
      row.querySelector('button').addEventListener('click', () => saveResultsToPort(idx));
      body.appendChild(row);
    });
  }

  // Create new port + save
  const divider = document.createElement('p');
  divider.className = 'modal-section-label';
  divider.style.marginTop = '16px';
  divider.textContent = 'หรือสร้าง Port ใหม่';
  body.appendChild(divider);

  const newRow = document.createElement('div');
  newRow.className = 'sri-new-row';
  newRow.innerHTML = `
    <input id="sri-new-name" type="text" placeholder="ชื่อ Port ใหม่" />
    <button id="sri-create-btn" class="btn btn-primary btn-sm">สร้าง + บันทึก</button>`;
  body.appendChild(newRow);

  newRow.querySelector('#sri-new-name').addEventListener('keydown', e => {
    if (e.key === 'Enter') newRow.querySelector('#sri-create-btn').click();
  });
  newRow.querySelector('#sri-create-btn').addEventListener('click', async () => {
    const name = newRow.querySelector('#sri-new-name').value.trim();
    if (!name) { newRow.querySelector('input').focus(); return; }
    try {
      const res = await fetch(`${API_BASE}/api/ports`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, tickers: [...r.tickers] }),
      });
      const json = await res.json();
      await fetchPorts();                          // refresh local list
      const idx = ports.findIndex(p => p.id === json.data.id);
      if (idx >= 0) await saveResultsToPort(idx);
    } catch (e) {
      alert('สร้าง Port ไม่สำเร็จ: ' + e.message);
    }
  });
}

async function saveResultsToPort(idx) {
  const r = state.results;
  const p = ports[idx];
  const last_run = {
    date: new Date().toISOString().slice(0, 10),
    delta: +deltaEl.value,
    tau: +tauEl.value,
    views: state.views.filter(v => v.enabled).map(v => ({ ...v })),
    weights: Object.fromEntries(r.tickers.map((t, i) => [t, r.wStar[i]])),
    metrics: { ...r.metrics },
  };
  try {
    await fetch(`${API_BASE}/api/ports/${p.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ last_run }),
    });
    await fetchPorts();
  } catch (e) {
    alert('บันทึกไม่สำเร็จ: ' + e.message);
    return;
  }
  closeSaveResultsModal();
  const el = $('#save-results-status');
  el.textContent = `✅ บันทึกลง Port "${p.name}" แล้ว`;
  el.className = 'status ok';
  setTimeout(() => { el.textContent = ''; el.className = 'status'; }, 3000);
}

// ── Formatting helpers ────────────────────────────────────────
function pct(x) { return (x * 100).toFixed(2) + '%'; }
function signed(x) { return (x >= 0 ? '+' : '') + (x * 100).toFixed(2) + '%'; }
function arrow(x) { return x > 0.0001 ? '↑' : x < -0.0001 ? '↓' : ''; }
function cls(x) { return x > 0 ? 'pos' : x < 0 ? 'neg' : ''; }
function round(x) { return Math.round(x * 10000) / 10000; }
function fmtCap(c) {
  if (!c) return '—';
  if (c >= 1e12) return (c / 1e12).toFixed(2) + 'T';
  if (c >= 1e9)  return (c / 1e9).toFixed(1) + 'B';
  if (c >= 1e6)  return (c / 1e6).toFixed(0) + 'M';
  return String(c);
}

// ── Reset to Market Portfolio (#10) ───────────────────────────
// Clears every view and recomputes — with no views w* collapses to w_mkt,
// a quick sanity check that the engine is behaving.
$('#reset-market').addEventListener('click', () => {
  if (!state.market) { alert('ดึงข้อมูลตลาดในหน้า Setup ก่อน'); goto('setup'); return; }
  state.views = [];
  renderViews();
  $('#run-bl').click();
});

// ── Init ──────────────────────────────────────────────────────
renderChips();
fetchPorts();   // async: loads ports from MongoDB → renderPortChips()
