# DCF Model Builder — Prompt README

## Overview

Build a complete, professional-grade **Discounted Cash Flow (DCF) valuation model** from scratch.
This prompt guides the AI to construct a fully functional DCF model with all required components,
formulas, assumptions, and sensitivity analysis — suitable for equity research, investment analysis,
or academic use.

---

## What This Prompt Builds

A multi-stage DCF model covering:

1. **Revenue & FCF Projection** (5–10 year explicit forecast)
2. **WACC Calculation** (Cost of Equity via CAPM + Cost of Debt)
3. **Terminal Value** (Gordon Growth Model + Exit Multiple cross-check)
4. **PV of Cash Flows** (discounted FCF + discounted Terminal Value)
5. **Equity Bridge** (Enterprise Value → Equity Value → Price per Share)
6. **Sensitivity Analysis** (2D table: WACC vs. Terminal Growth Rate)

---

## Prompt

```
You are a senior financial modeler. Build a complete DCF (Discounted Cash Flow) valuation model
for the following company. Output the model as a structured table with clearly labeled sections,
formulas shown in brackets, and all assumptions explicitly stated.

---

### COMPANY INPUT
- Company Name: [COMPANY_NAME]
- Industry: [INDUSTRY]
- Base Year Revenue (Year 0): [REVENUE] (in USD millions)
- Current EBIT Margin: [EBIT_MARGIN]%
- Effective Tax Rate: [TAX_RATE]%
- D&A as % of Revenue: [DA_PCT]%
- CapEx as % of Revenue: [CAPEX_PCT]%
- Change in NWC as % of Revenue Growth: [NWC_PCT]%
- Forecast Period: [N] years
- Revenue Growth Rate (Year 1–[N]): [GROWTH_RATE]%
- Risk-Free Rate: [RF]%
- Equity Risk Premium: [ERP]%
- Beta (Levered): [BETA]
- Pre-Tax Cost of Debt: [KD]%
- Debt / (Debt + Equity): [D_WEIGHT]%
- Terminal Growth Rate: [TGR]%
- Shares Outstanding: [SHARES] million
- Net Debt (Debt minus Cash): [NET_DEBT] USD million

---

### OUTPUT STRUCTURE

#### SECTION 1 — Income Statement & FCF Projection
For each year from Year 1 to Year [N], calculate and display:

| Year | Revenue | EBIT | NOPAT | + D&A | - CapEx | - ΔNWC | = FCF |
|------|---------|------|-------|-------|---------|--------|-------|

Formulas:
- Revenue(t) = Revenue(t-1) × (1 + g)
- EBIT(t) = Revenue(t) × EBIT Margin
- NOPAT(t) = EBIT(t) × (1 - Tax Rate)
- FCF(t) = NOPAT(t) + D&A(t) - CapEx(t) - ΔNWC(t)

---

#### SECTION 2 — WACC Calculation
Display a step-by-step WACC build-up table:

| Component              | Formula                                     | Value |
|------------------------|---------------------------------------------|-------|
| Cost of Equity (Ke)    | Rf + β × ERP                               | ?%    |
| After-Tax Cost of Debt | Kd × (1 - Tax Rate)                        | ?%    |
| Weight of Equity (We)  | 1 - D/(D+E)                                | ?%    |
| Weight of Debt (Wd)    | D/(D+E)                                    | ?%    |
| WACC                   | Ke × We + Kd_after_tax × Wd                | ?%    |

---

#### SECTION 3 — Terminal Value
Calculate Terminal Value using both methods and display results side-by-side:

| Method                  | Formula                                      | Value (USD mm) |
|-------------------------|----------------------------------------------|----------------|
| Gordon Growth Model     | FCF(N) × (1 + TGR) / (WACC - TGR)          | ?              |
| Exit EV/EBITDA Multiple | EBITDA(N) × [Industry Multiple]              | ?              |
| Selected Terminal Value | [Explain rationale for which method used]    | ?              |

---

#### SECTION 4 — PV of Cash Flows
Discount each FCF and the Terminal Value back to Year 0:

| Year | FCF | Discount Factor [1/(1+WACC)^t] | PV of FCF |
|------|-----|-------------------------------|-----------|

Sum rows to arrive at:
- **Sum of PV(FCFs)** = ?
- **PV of Terminal Value** = ?
- **Enterprise Value (EV)** = Sum of PV(FCFs) + PV(Terminal Value)

---

#### SECTION 5 — Equity Bridge
| Item                          | Value (USD mm) |
|-------------------------------|----------------|
| Enterprise Value              | ?              |
| - Net Debt                    | [NET_DEBT]     |
| = Equity Value                | ?              |
| ÷ Shares Outstanding          | [SHARES] mm    |
| = **Implied Share Price**     | **$ ?**        |

---

#### SECTION 6 — Sensitivity Analysis
Build a 2D sensitivity table showing Implied Share Price across combinations of:
- WACC: WACC ± 2% in 0.5% increments
- Terminal Growth Rate: TGR ± 1.5% in 0.5% increments

| WACC \ TGR | TGR-1.5% | TGR-1.0% | TGR-0.5% | Base TGR | TGR+0.5% | TGR+1.0% | TGR+1.5% |
|-----------|---------|---------|---------|----------|---------|---------|---------|
| WACC-2.0% |         |         |         |          |         |         |         |
| ...       |         |         |         |          |         |         |         |
| Base WACC |         |         |         | **BASE** |         |         |         |
| ...       |         |         |         |          |         |         |         |
| WACC+2.0% |         |         |         |          |         |         |         |

Highlight the base case cell. Flag any cell where (WACC - TGR) ≤ 0 as "N/A (model breaks)".

---

#### SECTION 7 — Key Assumptions Summary
List all assumptions used in the model in one consolidated table:

| Assumption             | Value Used | Source / Rationale        |
|------------------------|------------|---------------------------|
| Revenue Growth Rate    | ?%         | [e.g., Industry avg / mgmt guidance] |
| EBIT Margin            | ?%         | [e.g., Historical average]           |
| WACC                   | ?%         | CAPM-based calculation               |
| Terminal Growth Rate   | ?%         | [e.g., Long-run GDP growth]          |
| Tax Rate               | ?%         | [e.g., Statutory / effective rate]   |
| Beta                   | ?          | [Source: Bloomberg / Damodaran]      |

---

### ADDITIONAL INSTRUCTIONS
- Show all formulas in brackets next to calculated values.
- Flag any assumption that significantly drives valuation (mark with ⚠️).
- Add a brief 3–5 sentence **Model Commentary** at the end summarizing: implied valuation vs. current price (if provided), key value drivers, and main risks to the model.
- If Revenue Growth Rate or EBIT Margin changes materially after Year 3, model a two-stage or
  three-stage growth scenario and note the transition.
- Use USD millions as the unit throughout. Round to 1 decimal place.
```

---

## How to Fill in the Variables

| Placeholder        | Description                                         | Example Value  |
|--------------------|-----------------------------------------------------|----------------|
| `[COMPANY_NAME]`   | Name of the company being valued                    | Apple Inc.     |
| `[INDUSTRY]`       | Industry sector                                     | Technology     |
| `[REVENUE]`        | Latest full-year revenue in USD millions            | 394,328        |
| `[EBIT_MARGIN]`    | EBIT as % of revenue                                | 30             |
| `[TAX_RATE]`       | Effective corporate tax rate (%)                    | 16             |
| `[DA_PCT]`         | Depreciation & Amortization as % of revenue        | 3              |
| `[CAPEX_PCT]`      | Capital Expenditure as % of revenue                 | 3.5            |
| `[NWC_PCT]`        | Change in Net Working Capital as % of rev growth   | 2              |
| `[N]`              | Forecast horizon in years                           | 5              |
| `[GROWTH_RATE]`    | Annual revenue growth rate during forecast period   | 8              |
| `[RF]`             | Risk-free rate (10-yr govt bond yield %)            | 4.5            |
| `[ERP]`            | Equity risk premium (%)                             | 5.5            |
| `[BETA]`           | Levered beta of the company                         | 1.2            |
| `[KD]`             | Pre-tax cost of debt (%)                            | 5.0            |
| `[D_WEIGHT]`       | Debt as proportion of total capital (%)             | 20             |
| `[TGR]`            | Terminal growth rate (%)                            | 3.0            |
| `[SHARES]`         | Shares outstanding in millions                      | 15,443         |
| `[NET_DEBT]`       | Total Debt minus Cash in USD millions               | -54,000        |

> **Tip:** For NET_DEBT, a negative number means the company is **net cash positive** (cash > debt),
> which adds to equity value in the bridge.

---

## Output Example (Partial)

```
SECTION 1 — FCF PROJECTION

| Year | Revenue  | EBIT   | NOPAT  | +D&A  | -CapEx | -ΔNWC | =FCF   |
|------|----------|--------|--------|-------|--------|-------|--------|
|  1   | 425,874  | 127,762| 107,320| 12,776| 14,906 | 1,244 | 103,946|
|  2   | 459,944  | 137,983| 115,906| 13,798| 16,098 | 1,343 | 112,263|
| ...  | ...      | ...    | ...    | ...   | ...    | ...   | ...    |

SECTION 2 — WACC

| Component           | Formula               | Value  |
|---------------------|-----------------------|--------|
| Cost of Equity (Ke) | 4.5% + 1.2 × 5.5%    | 11.1%  |
| After-Tax Kd        | 5.0% × (1 - 16%)     | 4.2%   |
| WACC                | 11.1%×80% + 4.2%×20% | 9.72%  |
```

---

## Tips for Best Results

- **Data sources:** Pull revenue, margins, and D&A/CapEx from the latest 10-K or annual report.
  Damodaran's website (pages.stern.nyu.edu/~adamodar) is excellent for industry betas and ERP.
- **Two-stage model:** If the company is in high-growth phase, split the forecast into
  Stage 1 (high growth, Years 1–5) and Stage 2 (normalized growth, Years 6–10) before Terminal Value.
- **Sanity check:** Terminal Value typically represents 60–80% of total DCF value for mature companies.
  If it's above 90%, consider whether the forecast period is too short.
- **Sensitivity first:** Always check that your base case WACC comfortably exceeds TGR by at least
  3–4 percentage points, or the Gordon Growth Model becomes unstable.

---

## Related Models to Build Next

| Model                      | When to Use                                      |
|----------------------------|--------------------------------------------------|
| **LBO Model**              | Leveraged buyout / private equity transactions   |
| **Comparable Company Analysis (Comps)** | Relative valuation using market multiples |
| **Dividend Discount Model (DDM)** | Mature, dividend-paying companies          |
| **Sum-of-the-Parts (SOTP)** | Conglomerates with distinct business segments  |
| **Monte Carlo DCF**        | Probabilistic valuation with variable ranges     |

---

*README version 1.0 — DCF Model Prompt for Antigravity*
