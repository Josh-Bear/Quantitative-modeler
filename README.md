# Quantitative Modeler

A personal library of quantitative finance models — built to be rigorous, automated, and reusable.

Each model lives in its own directory with a self-contained codebase and documentation.

---

## Models

| # | Model | Directory | Stack | Status |
|---|-------|-----------|-------|--------|
| 1 | [DCF Model Builder](#1-dcf-model-builder) | `dcf/` | JavaScript · Python | Live |
| 2 | [Apple DCF — Automated Pipeline](#2-apple-dcf--automated-pipeline) | `apple_dcf/` | Python · Excel | Live |
| 3 | LBO Model | `lbo/` | — | Planned |
| 4 | Comparable Company Analysis (Comps) | `comps/` | — | Planned |
| 5 | Dividend Discount Model (DDM) | `ddm/` | — | Planned |
| 6 | Monte Carlo DCF | `monte_carlo_dcf/` | — | Planned |
| 7 | Sum-of-the-Parts (SOTP) | `sotp/` | — | Planned |

---

## 1. DCF Model Builder

An interactive, browser-based DCF valuation tool with real-time sensitivity analysis.

**What it does**
- Builds a full 10-year FCF projection from user inputs
- Calculates WACC via CAPM
- Computes terminal value (Gordon Growth + Exit Multiple)
- Outputs a live sensitivity table (WACC × terminal growth rate)

**Stack:** Vanilla JS frontend · Python (Flask) backend

```bash
cd dcf
python server.py
# open http://localhost:5000
```

> See `dcf/README.md` for the full prompt template and variable guide.

---

## 2. Apple DCF — Automated Pipeline

A fully automated DCF model for Apple Inc. (AAPL) that pulls live data and generates a
professional Excel workbook — no manual data entry required.

**What it does**
- Fetches financials from SEC EDGAR XBRL API, Yahoo Finance, and FRED
- Projects 10 years of revenue across 5 segments (iPhone, Mac, iPad, Wearables, Services)
- Runs Best / Base / Worst case scenarios with a single scenario-switch cell
- Outputs a 24-tab Excel workbook with full 3-statement model, DCF, and sensitivity tables

**Stack:** Python · openpyxl · yfinance · SEC EDGAR API

```bash
cd apple_dcf
pip install yfinance pandas numpy openpyxl requests beautifulsoup4 lxml python-dateutil
python run.py
# output → apple_dcf/output/DCF_Model_Apple.xlsx
```

> See `apple_dcf/antigravity_brief.md` for the full architecture and data source map.

---

## Repository Structure

```
Quantitative-modeler/
├── dcf/                        # Interactive DCF web app
│   ├── index.html
│   ├── app.js
│   ├── dcf-engine.js
│   ├── chart-utils.js
│   ├── style.css
│   ├── server.py
│   └── README.md               # DCF prompt template & variable guide
│
├── apple_dcf/                  # Apple DCF automated pipeline
│   ├── run.py                  # Entry point
│   ├── src/
│   │   ├── fetch_data.py       # Data fetching (SEC, Yahoo Finance, FRED)
│   │   ├── build_model.py      # Excel workbook builder
│   │   ├── constants.py        # Fallback values & config
│   │   └── formatters.py       # Excel formatting utilities
│   ├── output/
│   │   └── DCF_Model_Apple.xlsx
│   └── antigravity_brief.md    # Full implementation spec
│
└── README.md
```

---

## Roadmap

Models are added in order of analytical dependency — intrinsic valuation first,
then relative valuation, then transaction-based, then probabilistic.

```
Intrinsic      DCF  →  DDM  →  Monte Carlo DCF
Relative       Comps  →  SOTP
Transaction    LBO
```
