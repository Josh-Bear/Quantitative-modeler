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

### QQQ High Growth Screener (`qqq_screener/`)
Screens NASDAQ-100 constituents (rank window configurable, default 26–100 by market cap) against a 5-point high-growth checklist and writes a 3-sheet Excel workbook.

```bash
cd qqq_screener
pip install yfinance pandas numpy openpyxl requests lxml
python run.py
# output → qqq_screener/output/qqq_screener_output.xlsx
```

A full run makes ~175 yfinance calls (ranking + screening) with a 0.5s delay between each (`RATE_LIMIT_SLEEP` in `constants.py`), so it takes ~2–3 minutes. Tune the rank window and pass/fail thresholds at the top of `src/constants.py`.

### Black-Litterman Web App (`black_litterman_model/`)
Interactive BL optimiser — vanilla JS engine + Python yfinance proxy. All BL math runs client-side in `engine/`.

```bash
cd black_litterman_model
pip install yfinance
python server.py
# open http://localhost:8770
python test.py   # 4-stock Thai proof-of-concept (reference output)
```

### BL LSTM+SVR View Generator (`bl_lstm_views/`)
ML pipeline that *generates* the Black-Litterman investor's views (Q vector) with a 4-layer LSTM + SVR, then optimises and backtests vs SPY. Produces `output/views.json` in the shape `black_litterman_model`'s `BL.compute()` consumes.

```bash
cd bl_lstm_views
pip install -r requirements.txt   # numpy, pandas, scikit-learn, yfinance, torch
python run.py --quick             # smoke test (2 stocks, 3 epochs)
python run.py                     # default (~6 sector-spread stocks)
python run.py --full              # paper scope (full DJI list, 400 epochs — slow)
python test.py                    # network-free BL-core sanity checks
```

`BL_LSTM_Portfolio.ipynb` is the same pipeline as a step-by-step Jupyter notebook (5 tech tickers) that calls the `src/` modules — open it from `bl_lstm_views/`. `Optuna_Hyperparameter_Search.ipynb` grid-searches the LSTM knobs (lr × batch × epochs = 27 combos/stock) via Optuna `GridSampler`, reusing `_train_one`; it only **reports** val-MSE tables + a heatmap (`OPTUNA_SMOKE=0` for the real 200/400/600 grid), never writing back to `constants.py`.

Unlike the other models, there is **no hardcoded `constants.py` fallback** (14 years of daily OHLCV is too large to inline); `fetch_data.py` caches to `output/cache/` and falls back to that, so the first run needs network. Requires PyTorch (uses Apple MPS when available). Tune everything in `src/constants.py`.

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

### `qqq_screener/` — Universe → Checklist pipeline

```
run.py                  # orchestrates: build universe → screen → console table → Excel
src/constants.py        # user config (rank window, thresholds) + fallback NASDAQ-100 list
src/universe.py         # Wikipedia constituents + market-cap ranking; caches .info per ticker
src/screener.py         # the 5-point checklist engine
src/excel_export.py     # 3-sheet workbook writer (Results / Shortlist / Data Quality)
```

`universe.py` fetches each ticker's `.info` once during the market-cap ranking pass and hands the cache to `screener.py`, so market data is not re-fetched. The Wikipedia constituent fetch uses `requests` with a browser User-Agent (the default urllib agent gets a 403) and falls back to the hardcoded list in `constants.py`.

`screener.py` scores each ticker 0–5; every check returns True / False / **None (N/A — data missing, not counted)** so missing fields never crash a run. Two non-obvious choices: Check 2 (revenue acceleration) matches the year-ago quarter **by date** (±45 days) because yfinance quarterly columns are irregularly spaced — positional indexing is wrong; Check 3 requires gross margin to be both high *and* expanding YoY. `_num()` filters `NaN` (note: `NaN is not None` is True, which previously leaked a `nan` Rule-of-40 value). Per-ticker failures and missing fields are recorded in the Data Quality sheet.

### `black_litterman_model/` — BL web app + `bl_lstm_views/` — ML view generator

Two sibling models. `black_litterman_model/` is the interactive optimiser: all BL math lives client-side in `engine/` (`matrix.js` Gauss-Jordan inverse, `stats.js` covariance/signals, `blacklitterman.js` core + constrained weights); `server.py` is only a yfinance proxy. See `black_litterman_model/CLAUDE.md` for the constraint policy (long-only → cap via water-filling, `DIAG_EPS=1e-4`, no-views identity).

`bl_lstm_views/` is the Python pipeline that *produces* the views the app would otherwise take by hand:

```
run.py                  # orchestrates fetch → indicators → train → views → BL → backtest → QA
src/constants.py        # ALL config; resolve_profile() maps --quick/--full to (universe, epochs)
src/fetch_data.py       # yfinance daily OHLCV + caps; caches to output/cache/ (no inline fallback)
src/indicators.py       # 8 features in PURE pandas/numpy (no pandas_ta / TA-Lib)
src/preprocessing.py    # train-only MinMax, 30-day windows, 5-day-ahead targets
src/lstm_model.py       # PyTorch 4×60 LSTM, one multi-output model per stock (Architecture B), MPS→CPU
src/svr_model.py        # sklearn SVR(RBF,C=5,ε=0.01): indicators → close/SMA-1 (stationary)
src/views.py            # composes LSTM+SVR → Q (annualised) + Ω (from test error) → views.json
src/black_litterman.py  # numpy BL (ports zzz.py + mirrors the JS engine's constraint policy)
src/backtest.py         # rolling 5-day rebalance vs SPY (annual return / Sharpe / max drawdown)
```

Non-obvious choices: SVR is **contemporaneous** (the 5-day horizon comes entirely from the LSTM forecasting indicators ahead — don't shift the SVR target); scaler is fit on the **train slice only**; view returns are annualised **linearly** to match the annualised prior Π. `bl_lstm_views/` supersedes the root scratch files `zzz.py` and `indicators/indicators.py`.

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
