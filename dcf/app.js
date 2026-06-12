/**
 * DCF Model Builder — Main Application Logic
 *
 * Handles UI interaction, rendering, Yahoo Finance fetch, and export.
 * Depends on: dcf-engine.js, chart-utils.js, html2pdf.js (CDN)
 */

// ═══════════════════════════════════════════════════════════════
//  GLOBAL STATE
// ═══════════════════════════════════════════════════════════════

let lastResults = null;   // cache for export

// ═══════════════════════════════════════════════════════════════
//  INITIALIZATION
// ═══════════════════════════════════════════════════════════════

document.addEventListener('DOMContentLoaded', () => {
    // Update exit multiple when industry changes
    document.getElementById('industry').addEventListener('change', (e) => {
        const mult = DCFEngine.getIndustryMultiple(e.target.value);
        document.getElementById('exitMultiple').value = mult;
    });

    // Toggle multi-stage fields
    document.getElementById('useMultiStage').addEventListener('change', (e) => {
        document.getElementById('multiStageFields').style.display = e.target.checked ? 'block' : 'none';
    });

    // Toggle margin fade field
    document.getElementById('useMarginFade').addEventListener('change', (e) => {
        document.getElementById('marginFadeField').style.display = e.target.checked ? 'block' : 'none';
    });

    // Calculate button
    document.getElementById('btnCalculate').addEventListener('click', calculateAndRender);

    // Reset button
    document.getElementById('btnReset').addEventListener('click', resetDefaults);

    // Fetch button
    document.getElementById('btnFetch').addEventListener('click', () => {
        const ticker = document.getElementById('tickerInput').value.trim().toUpperCase();
        if (ticker) fetchYahooFinance(ticker);
    });

    // Export buttons
    document.getElementById('btnExportCSV').addEventListener('click', exportCSV);
    document.getElementById('btnExportPDF').addEventListener('click', exportPDF);

    // Enter key on ticker input
    document.getElementById('tickerInput').addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            const ticker = e.target.value.trim().toUpperCase();
            if (ticker) fetchYahooFinance(ticker);
        }
    });
});

// ═══════════════════════════════════════════════════════════════
//  TOGGLE INPUT GROUPS
// ═══════════════════════════════════════════════════════════════

function toggleGroup(id) {
    document.getElementById(id).classList.toggle('collapsed');
}

// ═══════════════════════════════════════════════════════════════
//  GATHER INPUTS
// ═══════════════════════════════════════════════════════════════

function gatherInputs() {
    const val = (id) => parseFloat(document.getElementById(id).value) || 0;
    const str = (id) => document.getElementById(id).value.trim();
    const chk = (id) => document.getElementById(id).checked;

    return {
        companyName:       str('companyName'),
        industry:          str('industry'),
        revenue:           val('revenue'),
        growthRate:        val('growthRate'),
        n:                 Math.round(val('forecastYears')),
        useMultiStage:     chk('useMultiStage'),
        stageBreak:        Math.round(val('stageBreak')),
        growthRateStage2:  val('growthRateStage2'),
        ebitMargin:        val('ebitMargin'),
        taxRate:           val('taxRate'),
        daPct:             val('daPct'),
        capexPct:          val('capexPct'),
        nwcPct:            val('nwcPct'),
        useMarginFade:     chk('useMarginFade'),
        ebitMarginTerminal:val('ebitMarginTerminal'),
        rf:                val('rf'),
        erp:               val('erp'),
        beta:              val('beta'),
        kd:                val('kd'),
        dWeight:           val('dWeight'),
        tgr:               val('tgr'),
        exitMultiple:      val('exitMultiple'),
        shares:            val('shares'),
        netDebt:           val('netDebt'),
    };
}

// ═══════════════════════════════════════════════════════════════
//  VALIDATION
// ═══════════════════════════════════════════════════════════════

function validateInputs(inputs) {
    const errors = [];
    if (inputs.revenue <= 0) errors.push('Revenue must be positive.');
    if (inputs.n < 1 || inputs.n > 15) errors.push('Forecast period must be 1–15 years.');
    if (inputs.shares <= 0) errors.push('Shares outstanding must be positive.');
    if (inputs.beta <= 0) errors.push('Beta must be positive.');
    if (inputs.ebitMargin < 0 || inputs.ebitMargin > 100) errors.push('EBIT Margin must be 0–100%.');
    if (inputs.taxRate < 0 || inputs.taxRate > 100) errors.push('Tax Rate must be 0–100%.');
    return errors;
}

// ═══════════════════════════════════════════════════════════════
//  MAIN CALCULATE & RENDER
// ═══════════════════════════════════════════════════════════════

function calculateAndRender() {
    const inputs = gatherInputs();

    // Validate
    const errors = validateInputs(inputs);
    if (errors.length > 0) {
        errors.forEach(e => showToast(e, 'error'));
        return;
    }

    // Run DCF
    const results = DCFEngine.runFullDCF(inputs);
    lastResults = results;

    // Show results container
    document.getElementById('emptyState').style.display = 'none';
    document.getElementById('resultsContainer').style.display = 'block';

    // Render all sections
    renderHeroCards(results);
    renderSection1(results);
    renderSection2(results);
    renderSection3(results);
    renderSection4(results);
    renderSection5(results);
    renderSection6(results);
    renderSection7(results);
    renderSanityChecks(results);
    renderCommentary(results);

    // Render charts (with small delay for DOM to settle)
    requestAnimationFrame(() => {
        renderCharts(results);
    });

    showToast('DCF model calculated successfully', 'success');
}

// ═══════════════════════════════════════════════════════════════
//  HERO SUMMARY CARDS
// ═══════════════════════════════════════════════════════════════

function renderHeroCards(r) {
    const { equityBridge: eb, wacc: w, pvResults: pv, fcfProjection: fp } = r;
    const el = document.getElementById('heroCards');

    el.innerHTML = `
        <div class="hero-card">
            <div class="label">Implied Share Price</div>
            <div class="value primary">$${fmtN(eb.impliedSharePrice, 2)}</div>
            <div class="sub">${r.inputs.companyName}</div>
        </div>
        <div class="hero-card">
            <div class="label">Enterprise Value</div>
            <div class="value">${fmtM(pv.enterpriseValue)}</div>
            <div class="sub">USD millions</div>
        </div>
        <div class="hero-card">
            <div class="label">Equity Value</div>
            <div class="value positive">${fmtM(eb.equityValue)}</div>
            <div class="sub">EV − Net Debt</div>
        </div>
        <div class="hero-card">
            <div class="label">WACC</div>
            <div class="value">${fmtN(w.wacc, 2)}%</div>
            <div class="sub">Ke ${fmtN(w.ke,1)}% • Kd ${fmtN(w.kdAfterTax,1)}%</div>
        </div>
        <div class="hero-card">
            <div class="label">Year ${r.inputs.n} FCF</div>
            <div class="value positive">${fmtM(fp.fcfs[fp.fcfs.length-1])}</div>
            <div class="sub">USD millions</div>
        </div>
        <div class="hero-card">
            <div class="label">TV % of EV</div>
            <div class="value ${pv.tvAsPercentOfEV > 85 ? 'negative' : ''}">${fmtN(pv.tvAsPercentOfEV, 1)}%</div>
            <div class="sub">${pv.tvAsPercentOfEV > 85 ? '⚠️ High' : '✓ Normal'}</div>
        </div>
    `;
}

// ═══════════════════════════════════════════════════════════════
//  SECTION 1 — FCF Projection
// ═══════════════════════════════════════════════════════════════

function renderSection1(r) {
    const p = r.fcfProjection;
    const el = document.getElementById('section1Body');

    let html = `<table class="data-table">
        <thead><tr>
            <th>Year</th><th>Growth</th><th>Revenue</th><th>EBIT Margin</th>
            <th>EBIT</th><th>NOPAT</th><th>+ D&A</th><th>− CapEx</th>
            <th>− ΔNWC</th><th>= FCF</th>
        </tr></thead><tbody>`;

    for (let i = 0; i < p.years.length; i++) {
        html += `<tr>
            <td>Year ${p.years[i]}</td>
            <td>${fmtN(p.growthRates[i],1)}%</td>
            <td>${fmtM(p.revenues[i])}<span class="formula">[Rev × (1+g)]</span></td>
            <td>${fmtN(p.margins[i],1)}%</td>
            <td>${fmtM(p.ebits[i])}<span class="formula">[Rev × Margin]</span></td>
            <td>${fmtM(p.nopats[i])}<span class="formula">[EBIT × (1−t)]</span></td>
            <td>${fmtM(p.das[i])}</td>
            <td>${fmtM(p.capexs[i])}</td>
            <td>${fmtM(p.nwcs[i])}</td>
            <td style="color:var(--c-success);font-weight:700">${fmtM(p.fcfs[i])}</td>
        </tr>`;
    }

    html += `</tbody></table>`;
    el.innerHTML = html;
}

// ═══════════════════════════════════════════════════════════════
//  SECTION 2 — WACC
// ═══════════════════════════════════════════════════════════════

function renderSection2(r) {
    const w = r.wacc;
    const el = document.getElementById('section2Body');

    el.innerHTML = `<table class="data-table kv-table">
        <thead><tr><th>Component</th><th>Formula</th><th>Value</th></tr></thead>
        <tbody>
            <tr>
                <td>Cost of Equity (Ke)</td>
                <td>[${w.keFormula}]</td>
                <td style="font-weight:700">${fmtN(w.ke, 2)}%</td>
            </tr>
            <tr>
                <td>After-Tax Cost of Debt (Kd)</td>
                <td>[${w.kdFormula}]</td>
                <td style="font-weight:700">${fmtN(w.kdAfterTax, 2)}%</td>
            </tr>
            <tr>
                <td>Weight of Equity (We)</td>
                <td>[1 − D/(D+E)]</td>
                <td>${fmtN(w.we, 1)}%</td>
            </tr>
            <tr>
                <td>Weight of Debt (Wd)</td>
                <td>[D/(D+E)]</td>
                <td>${fmtN(w.wd, 1)}%</td>
            </tr>
            <tr class="total-row">
                <td>WACC</td>
                <td>[${w.waccFormula}]</td>
                <td style="font-weight:800">${fmtN(w.wacc, 2)}%</td>
            </tr>
        </tbody>
    </table>`;
}

// ═══════════════════════════════════════════════════════════════
//  SECTION 3 — Terminal Value
// ═══════════════════════════════════════════════════════════════

function renderSection3(r) {
    const tv = r.terminalValue;
    const el = document.getElementById('section3Body');

    el.innerHTML = `<table class="data-table kv-table">
        <thead><tr><th>Method</th><th>Formula</th><th>Value (USD mm)</th></tr></thead>
        <tbody>
            <tr>
                <td>Gordon Growth Model</td>
                <td>[${tv.gordonFormula}]</td>
                <td>${tv.gordonTV !== null ? fmtM(tv.gordonTV) : '<span style="color:var(--c-danger)">N/A</span>'}</td>
            </tr>
            <tr>
                <td>Exit EV/EBITDA Multiple</td>
                <td>[${tv.exitFormula}]</td>
                <td>${fmtM(tv.exitTV)}</td>
            </tr>
            <tr class="highlight">
                <td style="font-weight:700">✅ Selected Terminal Value</td>
                <td style="font-size:.75rem;color:var(--c-text-3)">${tv.method}</td>
                <td style="font-weight:800;color:var(--c-primary)">${fmtM(tv.selected)}</td>
            </tr>
        </tbody>
    </table>`;
}

// ═══════════════════════════════════════════════════════════════
//  SECTION 4 — PV of Cash Flows
// ═══════════════════════════════════════════════════════════════

function renderSection4(r) {
    const pv = r.pvResults;
    const fp = r.fcfProjection;
    const el = document.getElementById('section4Body');

    let html = `<table class="data-table">
        <thead><tr>
            <th>Year</th><th>FCF</th><th>Discount Factor</th><th>PV of FCF</th>
        </tr></thead><tbody>`;

    for (let i = 0; i < fp.years.length; i++) {
        html += `<tr>
            <td>Year ${fp.years[i]}</td>
            <td>${fmtM(fp.fcfs[i])}</td>
            <td>${fmtN(pv.discountFactors[i], 4)}<span class="formula">[1/(1+WACC)^${fp.years[i]}]</span></td>
            <td>${fmtM(pv.pvFCFs[i])}</td>
        </tr>`;
    }

    html += `
        <tr class="total-row">
            <td colspan="3">Sum of PV(FCFs)</td>
            <td style="font-weight:700">${fmtM(pv.sumPVFCFs)}</td>
        </tr>
        <tr class="total-row">
            <td colspan="3">PV of Terminal Value<span class="formula">[TV / (1+WACC)^${fp.years.length}]</span></td>
            <td style="font-weight:700">${fmtM(pv.pvTerminalValue)}</td>
        </tr>
        <tr class="total-row highlight">
            <td colspan="3" style="font-weight:800">Enterprise Value (EV)</td>
            <td style="font-weight:800;color:var(--c-primary);font-size:.95rem">${fmtM(pv.enterpriseValue)}</td>
        </tr>
    </tbody></table>`;

    el.innerHTML = html;
}

// ═══════════════════════════════════════════════════════════════
//  SECTION 5 — Equity Bridge
// ═══════════════════════════════════════════════════════════════

function renderSection5(r) {
    const eb = r.equityBridge;
    const el = document.getElementById('section5Body');
    const netDebtLabel = eb.netDebt < 0 ? '+ Net Cash' : '− Net Debt';
    const netDebtDisplay = eb.netDebt < 0 ? fmtM(Math.abs(eb.netDebt)) : `(${fmtM(eb.netDebt)})`;

    el.innerHTML = `<table class="data-table kv-table">
        <thead><tr><th>Item</th><th>Value (USD mm)</th></tr></thead>
        <tbody>
            <tr>
                <td>Enterprise Value</td>
                <td>${fmtM(eb.enterpriseValue)}</td>
            </tr>
            <tr>
                <td>${netDebtLabel}</td>
                <td>${netDebtDisplay}</td>
            </tr>
            <tr class="total-row">
                <td>= Equity Value</td>
                <td style="font-weight:700">${fmtM(eb.equityValue)}</td>
            </tr>
            <tr>
                <td>÷ Shares Outstanding</td>
                <td>${fmtM(eb.shares)} mm</td>
            </tr>
            <tr class="total-row highlight">
                <td style="font-weight:800;font-size:.95rem">= Implied Share Price</td>
                <td style="font-weight:800;color:var(--c-primary);font-size:1.1rem">$${fmtN(eb.impliedSharePrice, 2)}</td>
            </tr>
        </tbody>
    </table>`;
}

// ═══════════════════════════════════════════════════════════════
//  SECTION 6 — Sensitivity Table
// ═══════════════════════════════════════════════════════════════

function renderSection6(r) {
    const s = r.sensitivity;
    const el = document.getElementById('section6Body');

    // Find min/max for color scale (exclude N/A)
    let allVals = [];
    s.matrix.forEach(row => row.forEach(cell => {
        if (!cell.isNA && cell.value !== null) allVals.push(cell.value);
    }));
    const minVal = Math.min(...allVals);
    const maxVal = Math.max(...allVals);

    let html = `<table class="data-table sensitivity-table">
        <thead><tr><th>WACC \\ TGR</th>`;

    s.tgrValues.forEach(tgr => {
        const isBase = Math.abs(tgr - s.baseTGR) < 0.01;
        html += `<th${isBase ? ' style="color:var(--c-primary)"' : ''}>${fmtN(tgr,1)}%</th>`;
    });
    html += `</tr></thead><tbody>`;

    s.matrix.forEach((row, ri) => {
        const isBaseRow = Math.abs(s.waccValues[ri] - s.baseWACC) < 0.01;
        html += `<tr><td${isBaseRow ? ' style="color:var(--c-primary)"' : ''}>${fmtN(s.waccValues[ri],2)}%</td>`;

        row.forEach(cell => {
            if (cell.isNA) {
                html += `<td class="cell-na">N/A</td>`;
            } else {
                const color = heatmapColor(cell.value, minVal, maxVal);
                const cls = cell.isBase ? ' cell-base' : '';
                html += `<td class="${cls}" style="background:${color};color:#fff">$${fmtN(cell.value, 2)}</td>`;
            }
        });

        html += `</tr>`;
    });

    html += `</tbody></table>`;
    el.innerHTML = html;
}

// ═══════════════════════════════════════════════════════════════
//  SECTION 7 — Key Assumptions
// ═══════════════════════════════════════════════════════════════

function renderSection7(r) {
    const inp = r.inputs;
    const el = document.getElementById('section7Body');

    const rows = [
        ['Revenue Growth Rate', `${fmtN(inp.growthRate,1)}%`, inp.useMultiStage ? `Two-stage: ${fmtN(inp.growthRate,1)}% → ${fmtN(inp.growthRateStage2,1)}%` : 'Single-stage', true],
        ['EBIT Margin', `${fmtN(inp.ebitMargin,1)}%`, inp.useMarginFade ? `Fading to ${fmtN(inp.ebitMarginTerminal,1)}%` : 'Constant', true],
        ['WACC', `${fmtN(r.wacc.wacc,2)}%`, 'CAPM-based calculation', true],
        ['Terminal Growth Rate', `${fmtN(inp.tgr,1)}%`, 'Long-run GDP growth proxy', true],
        ['Tax Rate', `${fmtN(inp.taxRate,1)}%`, 'Effective tax rate', false],
        ['Beta (Levered)', `${inp.beta}`, 'Market data', false],
        ['D&A % of Revenue', `${fmtN(inp.daPct,1)}%`, 'Historical average', false],
        ['CapEx % of Revenue', `${fmtN(inp.capexPct,1)}%`, 'Historical average', false],
        ['Exit Multiple (EV/EBITDA)', `${inp.exitMultiple}x`, `${inp.industry} industry default`, false],
        ['Net Debt', `$${fmtM(inp.netDebt)}M`, inp.netDebt < 0 ? 'Net cash positive' : 'Net debt', false],
    ];

    let html = `<table class="data-table">
        <thead><tr><th>Assumption</th><th>Value</th><th>Source / Rationale</th></tr></thead>
        <tbody>`;

    rows.forEach(([name, value, source, isKey]) => {
        html += `<tr>
            <td>${isKey ? '⚠️ ' : ''}${name}</td>
            <td style="font-weight:600">${value}</td>
            <td style="color:var(--c-text-3)">${source}</td>
        </tr>`;
    });

    html += `</tbody></table>`;
    el.innerHTML = html;
}

// ═══════════════════════════════════════════════════════════════
//  SANITY CHECKS
// ═══════════════════════════════════════════════════════════════

function renderSanityChecks(r) {
    const el = document.getElementById('sanityChecks');
    if (r.sanityChecks.length === 0) {
        el.innerHTML = '';
        return;
    }

    el.innerHTML = r.sanityChecks.map(c => `
        <div class="check-item ${c.type}">
            <span class="check-icon">${c.icon}</span>
            <span>${c.message}</span>
        </div>
    `).join('');
}

// ═══════════════════════════════════════════════════════════════
//  MODEL COMMENTARY
// ═══════════════════════════════════════════════════════════════

function renderCommentary(r) {
    const inp = r.inputs;
    const eb = r.equityBridge;
    const pv = r.pvResults;
    const w = r.wacc;

    const tvPct = pv.tvAsPercentOfEV.toFixed(0);
    const spread = (w.wacc - inp.tgr).toFixed(1);

    let text = `Based on a ${inp.n}-year DCF model, ${inp.companyName} is valued at an implied share price of <strong>$${fmtN(eb.impliedSharePrice, 2)}</strong>, `;
    text += `with an Enterprise Value of $${fmtM(pv.enterpriseValue)}M. `;

    text += `The model uses a WACC of ${fmtN(w.wacc, 2)}% (WACC–TGR spread: ${spread}pp) `;
    text += `and a terminal growth rate of ${fmtN(inp.tgr, 1)}%. `;

    text += `Terminal Value accounts for ${tvPct}% of total Enterprise Value, `;
    text += tvPct > 80 ? 'which is elevated — extending the forecast horizon may improve robustness. ' : 'which is within the typical 60–80% range for mature companies. ';

    const keyDrivers = [];
    if (inp.growthRate > 7) keyDrivers.push('revenue growth');
    if (inp.ebitMargin > 25) keyDrivers.push('high operating margins');
    if (inp.netDebt < 0) keyDrivers.push('strong net cash position');
    if (keyDrivers.length > 0) {
        text += `Key value drivers include ${keyDrivers.join(', ')}. `;
    }

    text += `Main risks include sensitivity to WACC assumptions, margin compression, and macroeconomic headwinds.`;

    document.getElementById('commentaryText').innerHTML = text;
}

// ═══════════════════════════════════════════════════════════════
//  CHARTS
// ═══════════════════════════════════════════════════════════════

function renderCharts(r) {
    const fp = r.fcfProjection;
    const pv = r.pvResults;

    // FCF Bar Chart
    ChartUtils.drawFCFBarChart(
        document.getElementById('chartFCF'),
        fp.years,
        fp.fcfs
    );

    // Donut Chart
    ChartUtils.drawDonutChart(
        document.getElementById('chartDonut'),
        pv.sumPVFCFs,
        pv.pvTerminalValue
    );

    // Multi-Line Chart
    ChartUtils.drawMultiLineChart(
        document.getElementById('chartLines'),
        fp.years,
        [
            { label: 'Revenue', data: fp.revenues, color: ChartUtils.COLORS.cyan },
            { label: 'EBIT',    data: fp.ebits,    color: ChartUtils.COLORS.purple },
            { label: 'FCF',     data: fp.fcfs,     color: ChartUtils.COLORS.green },
        ]
    );
}

// ═══════════════════════════════════════════════════════════════
//  YAHOO FINANCE FETCH
// ═══════════════════════════════════════════════════════════════

/**
 * Industry map: Yahoo Finance industry string → our dropdown value
 */
const INDUSTRY_MAP = {
    'Consumer Electronics':          'Technology',
    'Software—Application':          'Technology',
    'Semiconductors':                'Technology',
    'Internet Content & Information':'Technology',
    'Drug Manufacturers':            'Healthcare',
    'Biotechnology':                 'Healthcare',
    'Medical Devices':               'Healthcare',
    'Oil & Gas E&P':                 'Energy',
    'Oil & Gas Integrated':          'Energy',
    'Banks—Diversified':             'Financials',
    'Insurance—Diversified':         'Financials',
    'Grocery Stores':                'Consumer Staples',
    'Household Products':            'Consumer Staples',
    'Auto Manufacturers':            'Consumer Discretionary',
    'Specialty Retail':              'Consumer Discretionary',
    'Telecom Services':              'Telecommunications',
    'REIT—Diversified':              'Real Estate',
    'Utilities—Regulated Electric':  'Utilities',
};

async function fetchYahooFinance(ticker) {
    const btn = document.getElementById('btnFetch');
    btn.disabled = true;
    btn.innerHTML = '<span class="loading-spinner"></span> Fetching...';

    // ── 1. Try local Python proxy first (most reliable, no CORS) ──
    const localProxyUrl = `http://localhost:8765/api/fetch?ticker=${encodeURIComponent(ticker)}`;

    try {
        const resp = await fetch(localProxyUrl, { signal: AbortSignal.timeout(5000) });
        if (resp.ok) {
            const json = await resp.json();
            if (json.ok && json.data) {
                btn.disabled = false;
                btn.innerHTML = '<span class="btn-icon">📡</span> Fetch';
                populateFormFromProxy(json.data);
                showToast(`✅ Loaded ${ticker} via local server`, 'success');
                return;
            }
        }
    } catch (_) {
        // Local proxy not running — fall through to CORS proxies
    }

    // ── 2. Fallback: public CORS proxies ──────────────────────────
    const yahooUrl = `https://query1.finance.yahoo.com/v10/finance/quoteSummary/${ticker}`
                   + `?modules=financialData,defaultKeyStatistics,summaryProfile`;

    const corsProxies = [
        `https://corsproxy.io/?${encodeURIComponent(yahooUrl)}`,
        `https://api.allorigins.win/raw?url=${encodeURIComponent(yahooUrl)}`,
    ];

    let raw = null;
    for (const proxyUrl of corsProxies) {
        try {
            const resp = await fetch(proxyUrl, { signal: AbortSignal.timeout(10000) });
            if (!resp.ok) continue;
            const json = await resp.json();
            if (json?.quoteSummary?.result?.[0]) { raw = json; break; }
        } catch (_) { continue; }
    }

    btn.disabled = false;
    btn.innerHTML = '<span class="btn-icon">📡</span> Fetch';

    if (!raw) {
        showToast(
            `⚠️ Could not fetch ${ticker}. Run server.py for reliable data, or enter values manually.`,
            'error'
        );
        return;
    }

    // Parse raw Yahoo Finance quoteSummary response
    try {
        const result = raw.quoteSummary.result[0];
        const fd = result.financialData        || {};
        const ks = result.defaultKeyStatistics || {};
        const sp = result.summaryProfile       || {};

        const payload = {
            ticker,
            companyName:       sp.longName || ticker,
            totalRevenue:      fd.totalRevenue?.raw,
            ebitMargins:       fd.ebitMargins?.raw,
            totalDebt:         fd.totalDebt?.raw,
            totalCash:         fd.totalCash?.raw,
            revenueGrowth:     fd.revenueGrowth?.raw,
            beta:              ks.beta?.raw,
            sharesOutstanding: ks.sharesOutstanding?.raw,
            industry:          sp.industry || '',
        };

        populateFormFromProxy(payload);
        showToast(`✅ Loaded ${ticker} via CORS proxy`, 'success');
    } catch (e) {
        showToast(`Error parsing data: ${e.message}`, 'error');
    }
}

/**
 * Populate sidebar form fields from a normalised data payload.
 * Works for both local proxy response and raw Yahoo quoteSummary.
 */
function populateFormFromProxy(d) {
    if (d.totalRevenue)      setVal('revenue',   (d.totalRevenue / 1e6).toFixed(0));
    if (d.ebitMargins != null) setVal('ebitMargin', (d.ebitMargins * 100).toFixed(1));
    if (d.beta != null)      setVal('beta',       d.beta.toFixed(2));
    if (d.sharesOutstanding) setVal('shares',     (d.sharesOutstanding / 1e6).toFixed(0));
    if (d.revenueGrowth != null) setVal('growthRate', (d.revenueGrowth * 100).toFixed(1));

    // Net Debt
    const debt = d.totalDebt || 0;
    const cash = d.totalCash || 0;
    setVal('netDebt', ((debt - cash) / 1e6).toFixed(0));

    // Company name
    if (d.companyName && d.companyName !== d.ticker) {
        document.getElementById('companyName').value = d.companyName;
    } else {
        document.getElementById('companyName').value = d.ticker || '';
    }

    // Industry → update exit multiple
    if (d.industry) {
        const mapped = INDUSTRY_MAP[d.industry];
        if (mapped) {
            const sel = document.getElementById('industry');
            sel.value = mapped;
            sel.dispatchEvent(new Event('change')); // trigger exit multiple update
        }
    }
}

// ═══════════════════════════════════════════════════════════════
//  EXPORT — CSV
// ═══════════════════════════════════════════════════════════════

function exportCSV() {
    if (!lastResults) {
        showToast('Please calculate the model first.', 'error');
        return;
    }

    const r = lastResults;
    const fp = r.fcfProjection;
    const pv = r.pvResults;
    const eb = r.equityBridge;
    const w  = r.wacc;
    let csv = '';

    // Header
    csv += `DCF Model - ${r.inputs.companyName}\n`;
    csv += `Generated: ${new Date().toISOString()}\n\n`;

    // Section 1
    csv += 'SECTION 1 - FCF Projection\n';
    csv += 'Year,Revenue,EBIT,NOPAT,D&A,CapEx,dNWC,FCF\n';
    for (let i = 0; i < fp.years.length; i++) {
        csv += `${fp.years[i]},${fp.revenues[i].toFixed(1)},${fp.ebits[i].toFixed(1)},${fp.nopats[i].toFixed(1)},${fp.das[i].toFixed(1)},${fp.capexs[i].toFixed(1)},${fp.nwcs[i].toFixed(1)},${fp.fcfs[i].toFixed(1)}\n`;
    }

    // Section 2
    csv += '\nSECTION 2 - WACC\n';
    csv += `Cost of Equity,${w.ke.toFixed(2)}%\n`;
    csv += `After-Tax Cost of Debt,${w.kdAfterTax.toFixed(2)}%\n`;
    csv += `WACC,${w.wacc.toFixed(2)}%\n`;

    // Section 4
    csv += '\nSECTION 4 - PV of Cash Flows\n';
    csv += 'Year,FCF,Discount Factor,PV of FCF\n';
    for (let i = 0; i < fp.years.length; i++) {
        csv += `${fp.years[i]},${fp.fcfs[i].toFixed(1)},${pv.discountFactors[i].toFixed(4)},${pv.pvFCFs[i].toFixed(1)}\n`;
    }

    // Section 5
    csv += '\nSECTION 5 - Equity Bridge\n';
    csv += `Enterprise Value,${pv.enterpriseValue.toFixed(1)}\n`;
    csv += `Net Debt,${eb.netDebt.toFixed(1)}\n`;
    csv += `Equity Value,${eb.equityValue.toFixed(1)}\n`;
    csv += `Shares Outstanding,${eb.shares.toFixed(1)}\n`;
    csv += `Implied Share Price,$${eb.impliedSharePrice.toFixed(2)}\n`;

    // Section 6
    csv += '\nSECTION 6 - Sensitivity (WACC vs TGR)\n';
    const s = r.sensitivity;
    csv += 'WACC\\TGR,' + s.tgrValues.map(t => t.toFixed(1) + '%').join(',') + '\n';
    s.matrix.forEach((row, ri) => {
        csv += s.waccValues[ri].toFixed(2) + '%,' +
            row.map(c => c.isNA ? 'N/A' : '$' + c.value.toFixed(2)).join(',') + '\n';
    });

    // Download
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href     = url;
    a.download = `DCF_${r.inputs.companyName.replace(/\s+/g, '_')}_${new Date().toISOString().slice(0,10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);

    showToast('CSV exported successfully', 'success');
}

// ═══════════════════════════════════════════════════════════════
//  EXPORT — PDF
// ═══════════════════════════════════════════════════════════════

function exportPDF() {
    if (!lastResults) {
        showToast('Please calculate the model first.', 'error');
        return;
    }

    if (typeof html2pdf === 'undefined') {
        // Fallback to window.print if html2pdf not loaded
        showToast('Opening print dialog — use "Save as PDF" option.', 'info');
        window.print();
        return;
    }

    showToast('Generating PDF...', 'info');

    const element = document.getElementById('resultsContainer');
    const companyName = lastResults.inputs.companyName.replace(/\s+/g, '_');

    const opt = {
        margin:       [10, 10, 10, 10],
        filename:     `DCF_${companyName}_${new Date().toISOString().slice(0,10)}.pdf`,
        image:        { type: 'jpeg', quality: 0.95 },
        html2canvas:  { scale: 2, useCORS: true, backgroundColor: '#0f172a' },
        jsPDF:        { unit: 'mm', format: 'a3', orientation: 'landscape' },
        pagebreak:    { mode: 'avoid-all', before: '.section' },
    };

    html2pdf().set(opt).from(element).save().then(() => {
        showToast('PDF exported successfully', 'success');
    }).catch((err) => {
        showToast('PDF export failed. Try using Print → Save as PDF.', 'error');
        console.error('PDF export error:', err);
    });
}

// ═══════════════════════════════════════════════════════════════
//  RESET DEFAULTS
// ═══════════════════════════════════════════════════════════════

function resetDefaults() {
    const defaults = {
        companyName: 'Apple Inc.', industry: 'Technology',
        revenue: 391035, growthRate: 5, forecastYears: 5,
        stageBreak: 3, growthRateStage2: 3,
        ebitMargin: 31.5, taxRate: 16, daPct: 3, capexPct: 2.8, nwcPct: 2,
        ebitMarginTerminal: 25,
        rf: 4.3, erp: 5.5, beta: 1.24, kd: 3.5, dWeight: 15,
        tgr: 3, exitMultiple: 20,
        shares: 15115, netDebt: -49000,
    };

    Object.entries(defaults).forEach(([id, val]) => {
        const el = document.getElementById(id);
        if (el) el.value = val;
    });

    document.getElementById('useMultiStage').checked = false;
    document.getElementById('useMarginFade').checked = false;
    document.getElementById('multiStageFields').style.display = 'none';
    document.getElementById('marginFadeField').style.display = 'none';
    document.getElementById('tickerInput').value = 'AAPL';

    showToast('Reset to Apple Inc. defaults', 'info');
}

// ═══════════════════════════════════════════════════════════════
//  UTILITY FUNCTIONS
// ═══════════════════════════════════════════════════════════════

/** Format number with commas and decimals */
function fmtN(n, decimals = 1) {
    if (n == null || isNaN(n)) return '—';
    return n.toLocaleString('en-US', {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
    });
}

/** Format monetary value in millions with commas */
function fmtM(n) {
    if (n == null || isNaN(n)) return '—';
    return n.toLocaleString('en-US', {
        minimumFractionDigits: 1,
        maximumFractionDigits: 1,
    });
}

/** Set input value */
function setVal(id, val) {
    const el = document.getElementById(id);
    if (el) el.value = val;
}

/** Generate heatmap color based on value position in range */
function heatmapColor(value, min, max) {
    if (max === min) return 'rgba(16,185,129,0.5)';
    const ratio = (value - min) / (max - min); // 0 = min (red), 1 = max (green)

    // Red (#ef4444) → Yellow (#f59e0b) → Green (#10b981)
    let r, g, b;
    if (ratio < 0.5) {
        const t = ratio * 2;
        r = Math.round(239 + (245 - 239) * t);
        g = Math.round(68  + (158 - 68)  * t);
        b = Math.round(68  + (11  - 68)  * t);
    } else {
        const t = (ratio - 0.5) * 2;
        r = Math.round(245 + (16  - 245) * t);
        g = Math.round(158 + (185 - 158) * t);
        b = Math.round(11  + (129 - 11)  * t);
    }

    return `rgba(${r},${g},${b},0.55)`;
}

/** Toast notification */
function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    const icons = { success: '✅', error: '❌', info: 'ℹ️' };

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `<span class="toast-icon">${icons[type] || 'ℹ️'}</span><span>${message}</span>`;

    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(40px)';
        toast.style.transition = 'all 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}
