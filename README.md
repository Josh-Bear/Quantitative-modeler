# Quantitative Modeler

A personal library of quantitative finance models — built to be rigorous, automated, and reusable.

Each model lives in its own directory with a self-contained codebase and documentation.

---

## Models

| # | Model | Directory | Stack | Status |
|---|-------|-----------|-------|--------|
| 1 | [DCF Model Builder](#1-dcf-model-builder) | `dcf/` | JavaScript · Python | Live |
| 2 | [Apple DCF — Automated Pipeline](#2-apple-dcf--automated-pipeline) | `apple_dcf/` | Python · Excel | Live |
| 3 | [QQQ High Growth Screener](#3-qqq-high-growth-screener) | `qqq_screener/` | Python · Excel | Live |
| 4 | [Black-Litterman Portfolio Optimizer](#4-black-litterman-portfolio-optimizer) | `black_litterman_model/` | JavaScript · React · FastAPI | Live |
| 5 | [BL LSTM+SVR View Generator](#5-bl-lstmsvr-view-generator) | `bl_lstm_views/` | Python · PyTorch | Live |
| 6 | [ML Black-Litterman Backtest](#6-ml-black-litterman-backtest) | `bl_model_port_optimization/` | Python · PyTorch | Live |
| 7 | [SET50 Order Execution Simulator](#7-set50-order-execution-simulator) | `order_execution/` | Python · Excel | Live |
| 8 | [Execution Algorithm Research](#8-execution-algorithm-research) | `execution_research/` | Python · Jupyter | Live |
| 9 | LBO Model | `lbo/` | — | Planned |
| 10 | Comparable Company Analysis (Comps) | `comps/` | — | Planned |
| 11 | Dividend Discount Model (DDM) | `ddm/` | — | Planned |
| 12 | Monte Carlo DCF | `monte_carlo_dcf/` | — | Planned |
| 13 | Sum-of-the-Parts (SOTP) | `sotp/` | — | Planned |

Generated files (`output/`, `cache/`, `data/`) are gitignored — run the model to recreate them.

---

## 1. DCF Model Builder

An interactive, browser-based DCF valuation tool with real-time sensitivity analysis.

**What it does**
- Builds a full 10-year FCF projection from user inputs
- Calculates WACC via CAPM
- Computes terminal value (Gordon Growth + Exit Multiple)
- Outputs a live sensitivity table (WACC × terminal growth rate)

**Stack:** Vanilla JS frontend · Python stdlib `http.server` backend (yfinance proxy)

```bash
cd dcf
pip install yfinance
python server.py
# open http://localhost:8765
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

## 3. QQQ High Growth Screener

Screens NASDAQ-100 constituents (ranked 26–100 by market cap, configurable)
against a 5-point high-growth checklist using live yfinance data.

**What it does**
- Pulls NASDAQ-100 constituents from Wikipedia and ranks them by live market cap
- Scores each name 0–5 on: revenue growth, revenue acceleration, gross margin
  (high & expanding), Rule of 40, and analyst EPS revisions
- Outputs a scored console table plus a 3-sheet Excel workbook (Results,
  Shortlist, Data Quality)

**Stack:** Python · yfinance · openpyxl

```bash
cd qqq_screener
pip install yfinance pandas numpy openpyxl requests lxml
python run.py
# output → qqq_screener/output/qqq_screener_output.xlsx
```

> See `qqq_screener/README.md` for the checklist definitions and config options,
> and `qqq_screener/task_brief.md` for the original brief.

---

## 4. Black-Litterman Portfolio Optimizer

Interactive web app that blends market-implied equilibrium returns with your own
views (manual, signal-generated, or ML-generated) and produces optimal weights.

**What it does**
- Fetches live prices + market caps, builds Σ and the equilibrium prior Π
- Combines views into the BL posterior μ_BL, then long-only constrained weights
- Shows weight table, efficient frontier, and CSV export; saves Ports to MongoDB

**Stack:** Vanilla JS engine (`engine/`) · legacy JS UI or React/Vite UI (`frontend/`) · FastAPI `backend/`

```bash
cd black_litterman_model
pip install yfinance
python server.py
# open http://localhost:8770
```

> See `black_litterman_model/README.md` for the React frontend, backend, and Docker setup.

---

## 5. BL LSTM+SVR View Generator

ML pipeline that generates the Black-Litterman investor's views (Q vector) with a
4-layer LSTM + SVR, then optimises and backtests vs SPY. Exports `output/views.json`
in the shape the BL web app consumes.

**Stack:** Python · PyTorch · scikit-learn · yfinance

```bash
cd bl_lstm_views
pip install -r requirements.txt
python run.py --quick   # smoke test
python run.py           # default
```

> See `bl_lstm_views/README.md`.

---

## 6. ML Black-Litterman Backtest

ML-driven Black-Litterman optimiser with a quarterly walk-forward backtest: per-stock
LSTM→SVR forecasts, top-2-per-sector stock selection, BL posterior, Max-Sharpe
portfolio, benchmarked against S&P 500 buy-and-hold.

**Stack:** Python · PyTorch · scikit-learn · TA-Lib · yfinance

```bash
cd bl_model_port_optimization
pip install -r requirements.txt   # brew install ta-lib first
python run.py --quick              # smoke test
python run.py                      # default profile
```

> Design spec lives in `bl_model_port_optimization/bl_spec/`; see `bl_model_port_optimization/CLAUDE.md`.

---

## 7. SET50 Order Execution Simulator

Simulates sending a 10-stock SET50 portfolio's orders to the market on hourly bars and
compares MARKET (one shot) with TWAP (5 hourly slices).

**What it does**
- SMA crossover + RSI signals → pre-trade checks (cash, holdings, weight bounds, board lots)
- Next-bar execution with half-spread, square-root impact on each bar's real traded value, commission + VAT
- Implementation Shortfall decomposition, fill vs TWAP / market VWAP, NAV stats → 7-sheet Excel

**Stack:** Python · pandas · openpyxl

```bash
cd order_execution
pip install -r requirements.txt
python run.py              # needs SET50_*.csv (hourly, long format) in the folder
python run.py --synthetic  # runs without data
```

> See `order_execution/README.md` for the data format and assumptions.

---

## 8. Execution Algorithm Research

Controlled experiment: 8,000 parent orders (1–25 % of a 100M NAV, point-in-time Top-10
SET50 names, out-of-sample 2025–26), each executed by MARKET, TWAP, VWAP and POV on
real hourly bars; paired statistical tests, sensitivity and an in-sample check.

**Stack:** Python · pandas · scipy · Jupyter

```bash
cd execution_research
pip install -r requirements.txt
jupyter notebook Research.ipynb   # the study
python run.py                     # text report + CSVs
```

> Uses the `SET50_*.csv` files in `order_execution/`. See `execution_research/README.md`.

---

## Repository Structure

```
Quantitative-modeler/
├── dcf/                          # Interactive DCF web app
├── apple_dcf/                    # Apple DCF automated pipeline → Excel
├── qqq_screener/                 # NASDAQ-100 high-growth screener → Excel
├── black_litterman_model/        # BL optimiser web app (JS engine, React UI, FastAPI backend)
├── bl_lstm_views/                # LSTM+SVR view generator for BL
├── bl_model_port_optimization/   # ML BL walk-forward backtest (spec in bl_spec/)
├── order_execution/              # SET50 hourly order-execution simulator (MARKET vs TWAP)
├── execution_research/           # execution-algo research notebook (MARKET/TWAP/VWAP/POV)
├── CLAUDE.md                     # Guidance for Claude Code
└── README.md
```

Each Python model follows the same layout: `run.py` entry point, `src/` modules,
`src/constants.py` for config/fallback data, and a gitignored `output/`.

---

## Roadmap

Models are added in order of analytical dependency — intrinsic valuation first,
then relative valuation, then transaction-based, then probabilistic.

```
Intrinsic      DCF  →  DDM  →  Monte Carlo DCF
Relative       Comps  →  SOTP
Transaction    LBO
Portfolio      Black-Litterman  →  ML views  →  Walk-forward backtest
Execution      Order-execution simulator  →  Execution-algorithm research
```
