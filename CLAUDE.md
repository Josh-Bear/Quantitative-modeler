# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Repo Is

A personal library of quantitative finance models. Each model is self-contained in its own directory. Models are built in order of analytical dependency: intrinsic valuation (DCF, DDM, Monte Carlo) → relative (Comps, SOTP) → transaction (LBO).

## Running the Models

### DCF Web App (`dcf/`)
Interactive browser-based DCF with real-time sensitivity analysis. Vanilla JS frontend + Python Flask-lite backend (stdlib `http.server`, no Flask required).

```bash
cd dcf
pip install yfinance
python server.py
# open http://localhost:8765
```

Backend serves static files and proxies `/api/fetch?ticker=XX` via yfinance. All DCF math runs client-side in `dcf-engine.js`.

### Apple DCF Pipeline (`apple_dcf/`)
Fully automated pipeline that fetches live data and writes a 24-tab Excel workbook.

```bash
cd apple_dcf
pip install yfinance pandas numpy openpyxl requests beautifulsoup4 lxml python-dateutil
python run.py
# output → apple_dcf/output/DCF_Model_Apple.xlsx
```

Optional: set `FMP_API_KEY` env var to pull live segment revenue from Financial Modeling Prep instead of the hardcoded fallback.

## Architecture

### `apple_dcf/` — Data → Model pipeline

```
run.py                  # orchestrates: fetch → build → QA → print summary
src/fetch_data.py       # live data pipeline; always falls back to constants.py on failure
src/constants.py        # FALLBACK values and HIST_* hardcoded historical data (5 years)
src/build_model.py      # writes the Excel workbook
src/formatters.py       # openpyxl formatting helpers
```

`fetch_data.py` pulls from four sources in order: yfinance (market data), FRED (10Y Treasury + breakeven inflation), Damodaran (ERP), SEC EDGAR XBRL API (financials). Every fetch is wrapped in try/except; missing data falls back to `constants.py` rather than crashing. All monetary values are in USD millions.

`run.py` runs a QA checklist after building: balance sheet balances, WACC > TGR for all scenarios, implied price within 30–300% of market, TV < 90% of EV, FCF always positive.

### `dcf/` — Web app

```
index.html / style.css  # UI
app.js                  # event handling, populates inputs from API, calls engine
dcf-engine.js           # pure DCF math: FCF projection, WACC, TV, sensitivity table
chart-utils.js          # sensitivity table rendering
server.py               # stdlib HTTP server; /api/fetch proxies yfinance
```

`dcf-engine.js` is the core — all six sections (FCF projection, WACC, terminal value, PV, equity bridge, sensitivity) are computed here with no external dependencies.

## Adding a New Model

Each model gets its own top-level directory. Pattern from existing models:
- Entry point script at the directory root (e.g., `run.py`)
- `src/` for modules, `output/` for generated files
- Hardcoded fallback data in a `constants.py` so the model can run without live API access
- Brief specced in `<dirname>/antigravity_brief.md` or similar

Planned models: `lbo/`, `comps/`, `ddm/`, `monte_carlo_dcf/`, `sotp/`.

## Data Sources Used Across Models

| Source | What it provides | Notes |
|--------|-----------------|-------|
| yfinance | Market price, shares, beta, margins, growth | Primary for market data |
| SEC EDGAR XBRL | 5-year financial statements | `data.sec.gov/api/xbrl/companyfacts/CIK<cik>.json` |
| FRED | 10Y Treasury rate, breakeven inflation | Public CSV endpoint |
| Damodaran | Equity risk premium (US) | Scraped from NYU Stern page |
| FMP (optional) | Segment revenue breakdown | Requires `FMP_API_KEY` env var |
| Wikipedia | Index component lists | Parsed with `pd.read_html` |
