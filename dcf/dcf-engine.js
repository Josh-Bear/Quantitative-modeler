/**
 * DCF Engine — Core Discounted Cash Flow Calculation Engine
 * 
 * Pure financial logic with no DOM dependencies.
 * All monetary values are in USD millions unless otherwise noted.
 * Share price output is in actual USD.
 */

class DCFEngine {

    // ─── Industry Default Exit Multiples (EV/EBITDA) ───────────────
    static INDUSTRY_MULTIPLES = {
        'Technology':             20,
        'Healthcare':             15,
        'Consumer Staples':       14,
        'Consumer Discretionary': 15,
        'Financials':             12,
        'Energy':                  8,
        'Industrials':            12,
        'Real Estate':            18,
        'Telecommunications':     10,
        'Utilities':              10,
        'Materials':              10,
    };

    /**
     * Run the complete DCF model pipeline.
     * @param {Object} inputs — All model parameters
     * @returns {Object} Complete results for all 7 sections
     */
    static runFullDCF(inputs) {
        const wacc          = this.calculateWACC(inputs);
        const fcfProjection = this.projectFCF(inputs);

        const lastIdx  = fcfProjection.fcfs.length - 1;
        const fcfN     = fcfProjection.fcfs[lastIdx];
        const ebitdaN  = fcfProjection.ebitdas[lastIdx];

        const terminalValue = this.calculateTerminalValue(
            fcfN, ebitdaN, wacc.wacc, inputs.tgr, inputs.exitMultiple
        );

        const pvResults = this.discountCashFlows(
            fcfProjection.fcfs, terminalValue.selected, wacc.wacc
        );

        const equityBridge = this.equityBridge(
            pvResults.enterpriseValue, inputs.netDebt, inputs.shares
        );

        const sensitivity  = this.sensitivityMatrix(inputs, wacc.wacc);
        const sanityChecks = this.runSanityChecks(pvResults, terminalValue, wacc.wacc, inputs.tgr);

        return {
            inputs,
            wacc,
            fcfProjection,
            terminalValue,
            pvResults,
            equityBridge,
            sensitivity,
            sanityChecks,
        };
    }

    // ═══════════════════════════════════════════════════════════════
    // SECTION 1 — Revenue & FCF Projection
    // ═══════════════════════════════════════════════════════════════

    /**
     * Project Revenue → EBIT → NOPAT → FCF for each forecast year.
     * Supports single-stage and two-stage growth, plus optional margin fade.
     */
    static projectFCF(inputs) {
        const {
            revenue, ebitMargin, taxRate, daPct, capexPct, nwcPct, n,
            growthRate,
            growthRateStage2 = growthRate,
            stageBreak       = Math.ceil(n / 2),
            useMultiStage    = false,
            ebitMarginTerminal,
            useMarginFade    = false,
        } = inputs;

        const data = {
            years: [], revenues: [], ebits: [], nopats: [],
            das: [], capexs: [], nwcs: [], fcfs: [], ebitdas: [],
            margins: [], growthRates: [],
        };

        let prevRevenue = revenue;

        for (let t = 1; t <= n; t++) {
            // ── Growth rate ──
            const g = (useMultiStage && t > stageBreak)
                ? growthRateStage2 / 100
                : growthRate / 100;

            // ── EBIT Margin (optional linear fade) ──
            let margin;
            if (useMarginFade && ebitMarginTerminal !== undefined && n > 1) {
                const start = ebitMargin / 100;
                const end   = ebitMarginTerminal / 100;
                margin = start + (end - start) * ((t - 1) / (n - 1));
            } else {
                margin = ebitMargin / 100;
            }

            const rev      = prevRevenue * (1 + g);
            const ebit     = rev * margin;
            const nopat    = ebit * (1 - taxRate / 100);
            const da       = rev * (daPct / 100);
            const capex    = rev * (capexPct / 100);
            const deltaRev = rev - prevRevenue;
            const nwc      = deltaRev * (nwcPct / 100);
            const fcf      = nopat + da - capex - nwc;
            const ebitda   = ebit + da;

            data.years.push(t);
            data.revenues.push(rev);
            data.ebits.push(ebit);
            data.nopats.push(nopat);
            data.das.push(da);
            data.capexs.push(capex);
            data.nwcs.push(nwc);
            data.fcfs.push(fcf);
            data.ebitdas.push(ebitda);
            data.margins.push(margin * 100);
            data.growthRates.push(g * 100);

            prevRevenue = rev;
        }

        return data;
    }

    // ═══════════════════════════════════════════════════════════════
    // SECTION 2 — WACC Calculation
    // ═══════════════════════════════════════════════════════════════

    static calculateWACC(inputs) {
        const { rf, erp, beta, kd, taxRate, dWeight } = inputs;

        const ke         = rf / 100 + beta * (erp / 100);          // decimal
        const kdAfterTax = (kd / 100) * (1 - taxRate / 100);       // decimal
        const we         = 1 - dWeight / 100;                       // decimal
        const wd         = dWeight / 100;                           // decimal
        const wacc       = ke * we + kdAfterTax * wd;               // decimal

        return {
            ke:          ke * 100,
            kdAfterTax:  kdAfterTax * 100,
            we:          we * 100,
            wd:          wd * 100,
            wacc:        wacc * 100,
            keFormula:   `${rf.toFixed(1)}% + ${beta} × ${erp.toFixed(1)}%`,
            kdFormula:   `${kd.toFixed(1)}% × (1 − ${taxRate.toFixed(1)}%)`,
            waccFormula: `${(ke*100).toFixed(2)}% × ${(we*100).toFixed(1)}% + ${(kdAfterTax*100).toFixed(2)}% × ${(wd*100).toFixed(1)}%`,
        };
    }

    // ═══════════════════════════════════════════════════════════════
    // SECTION 3 — Terminal Value
    // ═══════════════════════════════════════════════════════════════

    static calculateTerminalValue(fcfN, ebitdaN, wacc, tgr, exitMultiple) {
        const w = wacc / 100;
        const g = tgr  / 100;

        // Gordon Growth Model
        let gordonTV = null;
        if (w > g) {
            gordonTV = (fcfN * (1 + g)) / (w - g);
        }

        // Exit EV/EBITDA Multiple
        const exitTV = ebitdaN * exitMultiple;

        // Default to Gordon if valid
        const selected = gordonTV !== null ? gordonTV : exitTV;
        const method   = gordonTV !== null ? 'Gordon Growth Model' : 'Exit EV/EBITDA Multiple';

        return {
            gordonTV,
            exitTV,
            selected,
            method,
            gordonFormula: gordonTV !== null
                ? `${this.fmt(fcfN)} × (1 + ${tgr.toFixed(1)}%) / (${wacc.toFixed(2)}% − ${tgr.toFixed(1)}%)`
                : 'N/A (WACC ≤ TGR)',
            exitFormula: `${this.fmt(ebitdaN)} × ${exitMultiple}x`,
        };
    }

    // ═══════════════════════════════════════════════════════════════
    // SECTION 4 — PV of Cash Flows
    // ═══════════════════════════════════════════════════════════════

    static discountCashFlows(fcfs, terminalValue, wacc) {
        const w = wacc / 100;
        const n = fcfs.length;

        const discountFactors = [];
        const pvFCFs          = [];

        for (let t = 0; t < n; t++) {
            const df = 1 / Math.pow(1 + w, t + 1);
            discountFactors.push(df);
            pvFCFs.push(fcfs[t] * df);
        }

        const sumPVFCFs      = pvFCFs.reduce((a, b) => a + b, 0);
        const pvTerminalValue = terminalValue / Math.pow(1 + w, n);
        const enterpriseValue = sumPVFCFs + pvTerminalValue;

        return {
            discountFactors,
            pvFCFs,
            sumPVFCFs,
            pvTerminalValue,
            enterpriseValue,
            tvAsPercentOfEV: (pvTerminalValue / enterpriseValue) * 100,
        };
    }

    // ═══════════════════════════════════════════════════════════════
    // SECTION 5 — Equity Bridge
    // ═══════════════════════════════════════════════════════════════

    static equityBridge(ev, netDebt, shares) {
        // netDebt < 0 means net cash → adds to equity
        const equityValue      = ev - netDebt;
        const impliedSharePrice = equityValue / shares;

        return { enterpriseValue: ev, netDebt, equityValue, shares, impliedSharePrice };
    }

    // ═══════════════════════════════════════════════════════════════
    // SECTION 6 — Sensitivity Matrix
    // ═══════════════════════════════════════════════════════════════

    static sensitivityMatrix(inputs, baseWACC) {
        const baseTGR = inputs.tgr;

        // WACC ± 2 % in 0.5 pp steps
        const waccValues = [];
        for (let w = baseWACC - 2; w <= baseWACC + 2.001; w += 0.5) {
            waccValues.push(Math.round(w * 100) / 100);
        }

        // TGR ± 1.5 % in 0.5 pp steps
        const tgrValues = [];
        for (let t = baseTGR - 1.5; t <= baseTGR + 1.501; t += 0.5) {
            tgrValues.push(Math.round(t * 100) / 100);
        }

        const matrix = [];
        for (const wacc of waccValues) {
            const row = [];
            for (const tgr of tgrValues) {
                if (wacc <= tgr) {
                    row.push({ value: null, isNA: true, isBase: false });
                } else {
                    const mod = { ...inputs, tgr };
                    const proj = this.projectFCF(mod);
                    const li   = proj.fcfs.length - 1;
                    const tv   = this.calculateTerminalValue(proj.fcfs[li], proj.ebitdas[li], wacc, tgr, inputs.exitMultiple);
                    const pv   = this.discountCashFlows(proj.fcfs, tv.selected, wacc);
                    const eq   = this.equityBridge(pv.enterpriseValue, inputs.netDebt, inputs.shares);

                    const isBase = Math.abs(wacc - baseWACC) < 0.01 && Math.abs(tgr - baseTGR) < 0.01;
                    row.push({ value: eq.impliedSharePrice, isNA: false, isBase });
                }
            }
            matrix.push(row);
        }

        return { waccValues, tgrValues, matrix, baseWACC, baseTGR };
    }

    // ═══════════════════════════════════════════════════════════════
    // Sanity Checks
    // ═══════════════════════════════════════════════════════════════

    static runSanityChecks(pvResults, terminalValue, wacc, tgr) {
        const checks = [];

        // TV dominance check
        if (pvResults.tvAsPercentOfEV > 85) {
            checks.push({
                type: 'warning',
                message: `Terminal Value = ${pvResults.tvAsPercentOfEV.toFixed(1)}% of EV (>85%). Consider extending forecast period.`,
                icon: '⚠️',
            });
        }

        // WACC–TGR spread
        const spread = wacc - tgr;
        if (spread > 0 && spread < 3) {
            checks.push({
                type: 'warning',
                message: `WACC–TGR spread is only ${spread.toFixed(1)} pp (recommend ≥ 3–4 pp). Model is sensitive.`,
                icon: '⚠️',
            });
        }
        if (spread <= 0) {
            checks.push({
                type: 'error',
                message: `WACC (${wacc.toFixed(2)}%) ≤ TGR (${tgr.toFixed(1)}%). Gordon Growth Model breaks!`,
                icon: '🚨',
            });
        }

        // Implied P/E sanity (rough check: EV / last-year NOPAT)
        return checks;
    }

    // ═══════════════════════════════════════════════════════════════
    // Helpers
    // ═══════════════════════════════════════════════════════════════

    /** Format number with 1 decimal place */
    static fmt(n) {
        if (n == null || isNaN(n)) return '—';
        return n.toLocaleString('en-US', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
    }

    /** Get industry default exit multiple */
    static getIndustryMultiple(industry) {
        return this.INDUSTRY_MULTIPLES[industry] || 12;
    }
}
