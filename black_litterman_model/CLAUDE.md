# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running

Two frontends exist — the legacy vanilla-JS app and a newer React app (`frontend/`,
see `docs/FRONTEND_REDESIGN.md`). Both call the same FastAPI `backend/` (`:8000`,
needs MongoDB) for Ports and ML Views. **Don't run `python server.py` and
`docker compose up` at the same time** — the Docker `frontend` service maps its
Vite dev server to host port `:8770`, the same port `server.py` binds directly.

Legacy (no build step, no npm):
```bash
pip install yfinance
python server.py
# open http://localhost:8770
```
The server serves static files directly and proxies Yahoo Finance to avoid CORS.

React (`frontend/`):
```bash
cd backend && uvicorn main:app --reload --port 8000   # once, for either frontend
cd ../frontend && npm install && npm run dev
# open http://localhost:5173
```

To verify the BL math independently (4-stock Thai proof of concept):
```bash
python test.py
```

## Architecture

All BL math runs **client-side** in `engine/`. The backend (`server.py`) is purely a Yahoo Finance proxy — it fetches monthly adjusted closes (default 3yr) + market cap per ticker via yfinance, then returns JSON. The FastAPI `backend/` (see below) is a separate service that both frontends use for Ports and ML Views.

### Data flow

```
Yahoo Finance (via server.py /api/data)
    → Stats.alignPrices() + returnsMatrix() + covariance()   [stats.js]
    → BL.compute()                                            [blacklitterman.js]
    → BL.optimalWeights() → BL.constrainWeights()
    → renderResults()                                         [app.js]
```

### engine/ modules (no DOM, no dependencies — testable in Node)

- **matrix.js** — pure linear algebra: `inverse` (Gauss-Jordan, partial pivoting), `multiply`, `transpose`, `matVec`, `scale`, `add`, `diag`, `regularize`, `quadForm`, `dot`
- **stats.js** — price alignment, monthly returns, annualised covariance (×12, sample denominator), market-cap weights, signals (momentum, zScore, relativeStrength)
- **blacklitterman.js** — BL core (`compute`), `optimalWeights`, `constrainWeights` (iterative water-filling), portfolio analytics (`portfolioReturn`, `portfolioVol`, `sharpe`, `trackingError`, `randomPortfolios`)

### app.js responsibilities

Owns all UI state (`state` object), tab navigation, ticker chips + autocomplete, Ports (saved via `backend/` → MongoDB, *not* localStorage — this repo doesn't use localStorage anywhere), view cards (manual + auto signal generator + ML views), and the Results page (weight table, bar chart, efficient-frontier canvas scatter, CSV/clipboard export).

### frontend/ (React + Vite + TypeScript)

A parallel implementation of the same 4 pages, built per `docs/FRONTEND_REDESIGN.md`:
Zustand stores (`marketStore`, `viewsStore`, `resultsStore`) replace `app.js`'s global
`state`; `src/api/client.ts` wraps the same `backend/` endpoints; `src/engine/index.ts`
loads `engine/matrix.js` / `stats.js` / `blacklitterman.js` as classic `<script>` tags
from `frontend/public/engine/`. That directory and `frontend/src/style.css` are
**generated** (gitignored) copies of the canonical root `engine/` and `style.css`:
the `sync` npm script regenerates them and runs automatically before `dev`/`build`;
`docker compose` bind-mounts the root originals instead. Routes: `/setup`,
`/views` (manual + auto), `/ml-views` (dedicated ML Views page, unlike the legacy
app which folds ML Views into the Views tab and gives ML diagnostics its own tab),
`/results`. `docker-compose.yml`'s `frontend` service runs this app's Vite dev
server, mapped to host `:8770`.

### ML views (`backend/ml_views.py` + POST `/api/ml-views`)

The "🤖 ML Views" button on the Views tab (design doc: `docs/ML_VIEWS_DESIGN.md`) trains a
per-stock LSTM encoder → SVR (Architecture A, 63-day forward-return target, daily 2y
data, 8 indicators mirroring `bl_model_port_optimization/src/features.py`) and returns
P (absolute per stock + relative top-vs-2nd per GICS sector), Q (r̂), and Ω in 3
selectable modes: `he-litterman` (P τΣ Pᵀ), `svr-residual` (validation-residual variance,
calibrated with separate abs/rel scales), `blend` (50/50). `parseMLViews()` in app.js
converts the payload into ordinary view cards — the BL engine (`engine/`) is untouched.
The endpoint lives in the FastAPI backend (`backend/routers/ml_views.py`, :8000), NOT in
the legacy `server.py`, because `app.js` sends all `/api/*` calls to `API_BASE`.
Needs `torch` + `scikit-learn` (see `backend/requirements.txt`); TA-Lib optional
(without it `ht_dcperiod` = 0.0 with a warning). Tickers that fail to fetch or train are
skipped and reported in `errors` — the run continues.

The payload also carries per-stock `diagnostics` (fetched days, train/val sample counts,
LSTM best-val MSE, SVR train/test MSE, r̂, ω — failed tickers included with their error),
rendered by `renderMLDiag()` on the "2 · ML Model" tab (pages are Setup → ML Model →
Views → Results). The 🤖 button on either the ML Model or Views tab triggers the same
`runMLViews()`; "test MSE" here means the held-out chronological 20% validation slice
(Architecture A has no separate test set, unlike the `bl_lstm_views` notebook).

## Key design decisions

**Σ regularization** — `DIAG_EPS = 1e-4` added to the diagonal before every inversion in `BL.compute()`. Bigger than the bare minimum so highly-correlated names don't blow up the inverse.

**Weight normalisation** — `optimalWeights()` intentionally returns raw un-normalised weights. Dividing by a near-zero sum can flip signs. `constrainWeights()` clamps to long-only first, *then* normalises, *then* applies per-stock min/max (5%/40%) via iterative water-filling.

**Auto-view Q clamping** — signal-generated views are clamped to `[Q_FLOOR=3%, Q_CAP=15%]` in `capQ()` so a runaway momentum signal can't push μ_BL to absurd levels.

**No-views identity** — when `P` is empty, `compute()` sets `M = τΣ` and `muBL = π`, so `w*` collapses exactly back to `w_mkt`. Use the "Reset to Market" button to sanity-check this.

**Covariance annualisation** — monthly returns ×12 in `Stats.covariance()`, so all outputs (Π, μ_BL, Sharpe, TE) read in annual terms.

## Known reference output

`test.py` (4 Thai stocks: PTT/AOT/KBANK/CPF, δ=3, τ=0.05, 3 views) produces:

```
w* = [PTT 53.36%, AOT 27.98%, KBANK 8.20%, CPF 10.45%]
```

The JS engine reproduces this to the basis point.
