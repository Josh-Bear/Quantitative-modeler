# Apple Inc. (AAPL) — Full DCF Model Build
## Implementation Brief for AI Coding Agent (Antigravity)

---

## 0. Mission Statement

Build a **complete, automated DCF valuation model for Apple Inc.** as a single Excel workbook
(`DCF_Model_Apple.xlsx`), generated end-to-end by Python. The workbook must mirror the
**tab architecture, formula logic, and analytical depth of the reference Tesla DCF model**
(`DCF_Model_Tesla.xlsx`), adapted to Apple's business structure.

The deliverable consists of:

1. A Python pipeline (`fetch_data.py`, `build_model.py`, `run.py`) that pulls all required
   inputs automatically from public APIs/sources — no manual data entry.
2. A generated Excel workbook with **10-year forecasts**, **3 scenarios** (Best / Base / Worst),
   full 3-statement projections, FCF build-up, WACC calculation, and DCF valuation with
   sensitivity tables.
3. A written rationale (embedded as cell comments or a "Notes" tab) explaining every
   non-trivial assumption.

---

## 1. Environment & Dependencies

```bash
pip install --break-system-packages \
    yfinance \
    pandas \
    numpy \
    openpyxl \
    requests \
    beautifulsoup4 \
    lxml \
    python-dateutil
```

| Library | Purpose |
|---|---|
| `yfinance` | Live share price, beta, shares outstanding, market cap |
| `requests` + SEC EDGAR API | Historical financial statements (10-K/10-Q), XBRL facts |
| `pandas` | Data wrangling, parsing SEC "R-file" HTML tables for segment data |
| `openpyxl` | Writing formulas, formatting, multi-sheet Excel output |
| `beautifulsoup4` / `lxml` | Scraping Damodaran datasets (ERP, ratings spreads) |

---

## 2. Data Source Map

This table is the **single source of truth** for where every Driver-tab input comes from.
The agent must implement one fetch function per row, with a hardcoded fallback value
(noted in the Appendix) if the live source fails.

| Input | Source | Method | Notes |
|---|---|---|---|
| Apple share price (latest close) | Yahoo Finance | `yfinance.Ticker("AAPL").history()` | Use latest trading day |
| Shares outstanding | Yahoo Finance | `Ticker("AAPL").info["sharesOutstanding"]` | Cross-check vs latest 10-K cover page |
| Levered Beta | Yahoo Finance | `Ticker("AAPL").info["beta"]` | 5Y monthly beta |
| 10-Year US Treasury Yield | FRED (St. Louis Fed) | CSV: `https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10` | Use most recent non-null value |
| Expected Inflation | FRED | CSV: `https://fred.stlouisfed.org/graph/fredgraph.csv?id=T10YIE` (10Y breakeven) | Proxy for long-run inflation |
| Market Risk Premium (US) | Damodaran (NYU Stern) | Scrape `https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/ctryprem.html` for "US Implied ERP" | Fallback: 5.0% |
| Corporate Tax Rate | Derived from SEC financials | `Provision for Income Taxes / Pretax Income` (avg of last 3 FY) | Effective rate, not statutory 21% |
| Cost of Debt / Bond Yield | Derived | `Total Interest Expense (TTM) / Total Debt (avg of period)` | Proxy for Apple's blended borrowing rate; cross-check against AAA spread (~0.5–0.8% over 10Y UST per Damodaran ratings spread table) |
| Income Statement (5yr history) | SEC EDGAR XBRL API | `https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json` | Parse `us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax`, `CostOfGoodsAndServicesSold`, `OperatingIncomeLoss`, etc. |
| Balance Sheet (5yr history) | SEC EDGAR XBRL API | Same endpoint, balance-sheet tags (`Assets`, `Liabilities`, `CashAndCashEquivalentsAtCarryingValue`, etc.) | Use instant (point-in-time) values |
| Segment Revenue (iPhone, Mac, iPad, Wearables, Services) | Financial Modeling Prep | `https://financialmodelingprep.com/api/v4/revenue-product-segmentation?symbol=AAPL&apikey=<KEY>` | Free-tier API key required; fallback = parse SEC 10-K "R" files via `pandas.read_html()` |
| Products vs Services Gross Margin | SEC EDGAR XBRL / 10-K MD&A | Tags split by `ProductOrServiceAxis` member (`Product` vs `Service`) | Used to derive segment-level GP% (see §6.4) |

> **API key handling:** Store any API keys in a local `.env` file (never hardcoded). If
> `FMP_API_KEY` is not set, fall back to the SEC R-file scraping method automatically —
> do not block the pipeline on a missing key.

---

## 3. Workbook Architecture (Tab List)

Build tabs in this exact order, mirroring the Tesla reference file:

| # | Tab Name | Type | Purpose |
|---|---|---|---|
| 1 | `Cover` | Static | Title page |
| 2 | `Drivers` | Input | Macro & company-level assumptions (CAPM inputs, tax, share price) |
| 3 | `Input -->` | Divider | Section separator |
| 4 | `P&L Input` | Historical | 5-year actual income statement, segment revenue, KPIs |
| 5 | `Balance Sheet Input` | Historical | 5-year actual balance sheet, KPIs (ROA, ROE, liquidity) |
| 6 | `Workings -->` | Divider | Section separator |
| 7 | `Segment - iPhone` | Working | Units, ASP, revenue, GP% (3 scenarios) |
| 8 | `Segment - Mac` | Working | Same structure |
| 9 | `Segment - iPad` | Working | Same structure |
| 10 | `Segment - Wearables` | Working | Same structure |
| 11 | `Segment - Services` | Working | Subscriber/revenue build, GP% |
| 12 | `Revenue & GP Summary` | Working | Aggregates all segments into Total Revenue / Total GP |
| 13 | `Opex` | Working | R&D and SG&A as % of revenue, with comparables |
| 14 | `PP&E` | Working | Fixed asset roll-forward, D&A schedule |
| 15 | `Working Capital` | Working | DSO/DIO/DPO-driven NWC schedule |
| 16 | `Financing & WACC` | Working | Debt schedule, CAPM, WACC build |
| 17 | `Output -->` | Divider | Section separator |
| 18 | `P&L` | Output | Full projected income statement (10yr × 3 scenarios) |
| 19 | `Balance Sheet` | Output | Full projected balance sheet, with balance check |
| 20 | `Cash Flow` | Output | FCF build-up (EBIT → NOPAT → UFCF) |
| 21 | `DCF` | Output | Discounting, terminal value, EV → equity value → price/share |
| 22 | `Sensitivity` | Output | 2D tables (WACC × terminal growth) for each scenario |
| 23 | `Scenario Summary` | Output | Side-by-side Best/Base/Worst price targets + rationale |
| 24 | `Notes & Assumptions` | Output | Plain-language rationale for every key assumption |

---

## 4. Apple's Reportable Segments (for the Granular Build)

Apple's 10-K discloses net sales for five categories. Use these as the segment tabs:

```
1. iPhone
2. Mac
3. iPad
4. Wearables, Home and Accessories
5. Services
```

> **Important data limitation:** Apple does **not** disclose COGS or gross profit by
> individual product category — only an aggregate split between **"Products"** and
> **"Services."** Therefore:
> - Revenue for iPhone/Mac/iPad/Wearables is forecast individually (units × ASP, or
>   YoY growth — see §6).
> - Gross margin for each *Products* sub-segment uses the **blended Products GP%**
>   as the base, then is adjusted by a **comparable-based differential** (see §6.4)
>   so that iPhone (higher scale/margin) ≠ Mac/iPad (lower scale/margin) — exactly how
>   the Tesla model differentiated Model 3 vs Model S vs Semi using comparable companies.
> - Services uses its own disclosed Services GP% directly (no proxy needed).

---

## 5. Data Fetching Pipeline — `fetch_data.py`

Structure as independent, individually-testable functions. Each returns a `pandas.DataFrame`
or `dict`, and each must `try/except` with a logged warning + fallback constant on failure.

```python
def fetch_market_data() -> dict:
    """Returns: share_price, shares_outstanding, beta"""

def fetch_macro_data() -> dict:
    """Returns: risk_free_rate (10Y UST), expected_inflation (10Y breakeven), mrp (Damodaran)"""

def fetch_sec_financials(cik="0000320193") -> dict:
    """
    Pulls company facts from SEC XBRL API.
    Returns 5 years of: Revenue, COGS (Products/Services split), R&D, SG&A,
    Operating Income, Other Income/Expense, Pretax Income, Tax Provision,
    Net Income, full Balance Sheet line items, D&A, CapEx, Interest Expense.
    """

def fetch_segment_revenue() -> pd.DataFrame:
    """
    Primary: FMP revenue-product-segmentation endpoint.
    Fallback: scrape SEC 10-K 'R' files for the segment table via pandas.read_html().
    Returns: 5-year revenue by [iPhone, Mac, iPad, Wearables, Services].
    """

def compute_derived_assumptions(financials: dict) -> dict:
    """
    Returns: effective_tax_rate (3yr avg), cost_of_debt (implied rate),
    products_gp_pct, services_gp_pct (each by year),
    da_pct_of_revenue, capex_pct_of_revenue, nwc_components (DSO/DIO/DPO)
    """
```

**SEC EDGAR request requirements:** Set a descriptive `User-Agent` header
(e.g. `"Apple DCF Research <your_email>"`) — SEC blocks anonymous/default user agents.

---

## 6. Tab-by-Tab Specification

### 6.1 `Drivers`

Single column of named cells (so all downstream formulas reference by name, not by tab/cell address):

| Row Label | Source | Example Value |
|---|---|---|
| Company | static | Apple |
| Currency | static | USD |
| Share price (latest) | `fetch_market_data` | $291.58 |
| Shares outstanding (mn) | `fetch_market_data` | ~14,750 |
| 10-Year Treasury Yield | `fetch_macro_data` | 4.55% |
| Market Risk Premium (US) | `fetch_macro_data` | 5.0% |
| Company Beta (levered) | `fetch_market_data` | 1.09 |
| Cost of Debt (implied) | `compute_derived_assumptions` | ~3.0–3.5% |
| Corporate tax rate (effective) | `compute_derived_assumptions` | ~16% |
| Expected inflation | `fetch_macro_data` | ~2.3% |
| Terminal growth rate (g) | manual, linked to inflation | = Expected inflation (or +0.5pp cap) |

### 6.2 `P&L Input` (Historical, 5 years + latest interim)

Replicate the structure already built by the user (verified correct), with rows:

```
Products revenue (split sub-rows: iPhone, Mac, iPad, Wearables)
Services revenue
Total revenues
Products COGS
Services COGS
Gross profit
Research and development
Selling, general and administrative
EBIT
Other income (expense), net
EBT
Provision for income taxes
Net Income

KPIs:
- Revenue % y-o-y (per segment)
- GP% products / GP% services / Overall GP%
- EBIT %, Net Income %
- (ROA, ROE — computed once Balance Sheet Input is linked)
```

### 6.3 `Balance Sheet Input`

Replicate structure already built (Apple version, with `Noncontrolling interests = 0`,
balance check row confirming `Total Assets = Total Liabilities + Equity`).

### 6.4 Segment Tabs (`Segment - iPhone`, `Mac`, `iPad`, `Wearables`)

Each tab follows the **Tesla "Revenue Automotive" pattern**:

```
Row: Units sold (historical from 10-K where disclosed; else back-solve from Revenue/ASP)
Row: Average Selling Price (ASP)
Row: Revenue = Units × ASP
Row: Y-o-Y growth %  (3 scenario blocks: Best / Base / Worst — see §7)

GP% block:
Row: Blended "Products GP%" (linked from P&L Input)
Row: Segment differential vs blended (e.g., iPhone = Products GP% + 3pp;
     Mac/iPad = Products GP% - 2pp) — derived from comparable companies
     (see Comparables sub-table below)
Row: Segment GP% = Blended Products GP% + Differential
Row: Gross Profit = Revenue × Segment GP%

Comparables sub-table (for differential rationale):
| Segment | Comparable companies | Their GP% | Rationale for Apple differential |
|---|---|---|---|
| iPhone | Samsung Mobile (IM division), Xiaomi smartphone segment | ~X% | Apple commands premium pricing → +differential |
| Mac | Dell, HP (PC segments) | ~X% | Commoditized hardware → lower differential |
| iPad | Same PC comparables | ~X% | Similar to Mac |
| Wearables | Garmin, Sonos | ~X% | Higher-margin niche hardware → +differential |
```

> Populate the comparables GP% by pulling each company's latest segment gross margin
> via `yfinance` financials where possible; otherwise hardcode from latest public filings
> with a source citation in the Notes tab.

### 6.5 `Segment - Services`

```
Row: Services revenue (historical + forecast)
Row: Y-o-Y growth % (3 scenarios — Services has historically grown 10-15%;
     Best case assumes App Store/Search-deal resilience, Worst case stresses
     a Google search-deal antitrust loss scenario — see §7)
Row: Services GP% (disclosed directly — no proxy needed; historically ~70-76%)
Row: Gross Profit = Revenue × GP%
```

### 6.6 `Revenue & GP Summary`

Sums all 5 segment tabs into Total Revenue and Total Gross Profit per year, per scenario.
This feeds directly into the `P&L` output tab. Include a check row:
`Total Revenue (Summary) - Total Revenue (P&L tab) = 0`.

### 6.7 `Opex`

```
R&D as % of revenue — historical trend (rising, ~7-8% of revenue) +
   comparables (Microsoft, Alphabet R&D as % of revenue) for sanity bounds
SG&A as % of revenue — historical trend (~6-7%) + comparables
Forecast: hold % of revenue flat at Base case 3yr-avg; Best case = slight
   operating leverage (% declines slowly); Worst case = % rises (cost inflation)
```

### 6.8 `PP&E`

Fixed-asset roll-forward (mirrors Tesla structure exactly):

```
Beginning PP&E
+ CapEx (% of revenue, historical avg ~3-3.5%)
- D&A (% of beginning PP&E, historical avg)
= Ending PP&E
```

### 6.9 `Working Capital`

```
DSO (Days Sales Outstanding) — from Accounts Receivable
DIO (Days Inventory Outstanding) — from Inventory
DPO (Days Payable Outstanding) — from Accounts Payable
Net Trade Cycle = DSO + DIO - DPO  (Apple is typically NEGATIVE — a key
   strength: suppliers finance Apple's working capital)
Forecast: hold at 3yr historical average per scenario (Worst case = trade
   cycle normalizes toward 0/positive, a working-capital drag)
```

### 6.10 `Financing & WACC`

```
Cost of Equity = Risk-free rate + Beta × MRP   (CAPM)
Cost of Debt = implied rate from §2 (after-tax = Cost of Debt × (1 - tax rate))
Capital structure weights = Debt / (Debt+Equity) and Equity / (Debt+Equity),
   using MARKET value of equity (share price × shares outstanding) and
   book value of debt (Total Debt from Balance Sheet)
WACC = We × Ke + Wd × Kd × (1 - tax rate)

Forecast: hold capital structure weights constant at current levels across
   all 10 years (Apple's structure is stable — unlike Tesla's deleveraging
   trajectory). Recompute WACC each year only if equity value changes
   materially under each scenario (optional refinement).
```

---

## 7. Scenario Framework — Best / Base / Worst Case

Every revenue-driving assumption must have **3 explicit values** with a one-sentence
rationale. Build this as a single "Scenario Switch" cell on the `Drivers` tab
(`1=Best, 2=Base, 3=Worst`, matching Tesla's `Selected case` mechanism) that all
segment tabs reference via `CHOOSE()` or `INDEX()`.

| Driver | Best Case | Base Case | Worst Case |
|---|---|---|---|
| iPhone revenue growth | Historical avg + 1pp — new product cycle (foldable/AI features) drives upgrade supercycle | Historical 3yr avg growth, in line with analyst consensus | Historical avg - 2pp — mature market, longer replacement cycles, China competition |
| Mac/iPad growth | Apple Silicon transition continues to drive share gains (+) | Flat-to-low single digit, in line with PC/tablet market growth | Market saturation, no major refresh cycle (≈0%) |
| Wearables growth | New category launch (e.g., health features, smart glasses) reaccelerates growth | Continuation of recent slowing growth trend | Category maturity, growth flattens to ~0% |
| Services growth | Continued ~13-15% growth; Search deal survives antitrust scrutiny | ~10-12%, moderating from recent highs | Google Search-deal revenue (~$20bn/yr) is lost due to antitrust ruling — one-time step-down + slower growth thereafter |
| Products GP% | Mix shift toward Services + supply chain efficiencies expand margin +1-2pp | Flat at 3yr historical average | Tariff/input cost pressure compresses margin -1-2pp |
| Services GP% | Continued mix shift to high-margin advertising/subscriptions, +1pp | Flat at historical average (~75%) | Regulatory pressure (App Store commission caps in EU/US) compresses margin -2-3pp |
| WACC | Lower — risk premium compresses in benign macro environment | Base CAPM-derived WACC | Higher — risk-free rate or beta rises in stressed macro environment |
| Terminal growth rate (g) | = long-run inflation + 0.5pp (Apple maintains real growth) | = long-run inflation | = long-run inflation - 0.5pp (mature company, real growth converges to zero) |

> Every cell that differs by scenario must carry an Excel **comment** with the
> rationale text from this table (use `openpyxl.comments.Comment`).

---

## 8. DCF Mechanics (`DCF` tab)

```
For each forecast year t = 1..10:
  EBIT(t)  = from P&L
  NOPAT(t) = EBIT(t) × (1 - tax rate)
  + D&A(t)
  - CapEx(t)
  - ΔNWC(t)
  = Unlevered FCF(t)

Discount factor(t) = 1 / (1 + WACC)^t
PV of FCF(t) = UFCF(t) × Discount factor(t)

Terminal Value (Gordon Growth) = UFCF(10) × (1+g) / (WACC - g)
PV of Terminal Value = Terminal Value × Discount factor(10)

Enterprise Value = Σ PV(FCF, t=1..10) + PV(Terminal Value)

Equity Bridge:
  + Cash & marketable securities (latest BS)
  - Total Debt (latest BS)
  = Equity Value
  ÷ Shares Outstanding
  = Implied Price per Share

Output this full waterfall for EACH of the 3 scenarios side by side.
Flag in red any scenario where (WACC - g) <= 0.02 (model becomes unstable).
```

### 8.1 `Sensitivity` Tab

For the **Base Case**, build a 2D data table:

```
Rows:    WACC from (Base WACC - 1.5%) to (Base WACC + 1.5%), step 0.25%
Columns: Terminal growth (g) from (Base g - 1.0%) to (Base g + 1.0%), step 0.25%
Cell value: Implied Price per Share
Highlight the intersection matching the Base Case inputs.
```

Repeat compact 1D sensitivity (WACC only) for Best and Worst cases.

---

## 9. Validation / QA Checklist (must pass before delivery)

```
[ ] Balance Sheet: Total Assets = Total Liabilities + Equity, every year, every scenario
[ ] Revenue & GP Summary tab Total Revenue == P&L tab Total Revenue (diff = 0)
[ ] Cash Flow: Closing cash(t) = Opening cash(t) + Net Cash Flow(t), rolls forward correctly
[ ] WACC - g > 0 in all scenarios (else flag explicitly)
[ ] All historical actuals (2021-2025) reconcile to SEC-filed 10-K figures within 0.1%
[ ] All scenario-dependent cells have an attached rationale comment
[ ] DCF implied price per share for Base Case is within a "sanity band"
    (e.g., 50%-200% of current market price) — if not, flag for review
    rather than silently outputting an extreme number
```

---

## 10. Execution Plan (order of operations for the agent)

```
1. Set up project structure: /data, /src, /output
2. Implement fetch_data.py — test each function independently, print outputs
3. Implement build_model.py:
   a. Write Cover, Drivers tabs (static + fetched values)
   b. Write P&L Input, Balance Sheet Input (5yr history from SEC XBRL)
   c. Write segment tabs (iPhone/Mac/iPad/Wearables/Services) with 3-scenario
      revenue & GP% builds
   d. Write Revenue & GP Summary, Opex, PP&E, Working Capital, Financing & WACC
   e. Write Output tabs: P&L, Balance Sheet, Cash Flow, DCF, Sensitivity,
      Scenario Summary
   f. Write Notes & Assumptions tab (auto-generated from rationale strings
      used in step c)
4. Run full QA checklist (§9) programmatically — print pass/fail per item
5. Save to /output/DCF_Model_Apple.xlsx
6. Print a summary to console: implied price/share for all 3 scenarios vs
   current market price
```

---

## 11. Appendix — Hardcoded Fallback Values (if live fetch fails)

| Input | Fallback Value | As-of |
|---|---|---|
| Share price | $291.58 | Jun 2026 |
| 10Y Treasury yield | 4.55% | Jun 2026 |
| Market Risk Premium | 5.0% | Damodaran, recurring est. |
| Beta | 1.09 | Yahoo Finance, Jun 2026 |
| Corporate tax rate (effective) | 16% | 3yr avg FY2023-2025 |
| Expected inflation | 3.0% | IMF WEO |
| Cost of debt | 5.0% | AAA spread over 10Y UST |

---

*End of brief. This document is the complete specification — implement directly without
requesting further clarification on structure; only ask if a specific API/data source is
unreachable and no fallback is specified above.*
