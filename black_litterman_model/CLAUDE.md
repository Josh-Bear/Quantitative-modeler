# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running

```bash
pip install yfinance
python server.py
# open http://localhost:8770
```

No build step, no npm. The server serves static files directly and proxies Yahoo Finance to avoid CORS.

To verify the BL math independently (4-stock Thai proof of concept):
```bash
python test.py
```

## Architecture

All BL math runs **client-side** in `engine/`. The backend (`server.py`) is purely a Yahoo Finance proxy — it fetches monthly adjusted closes (default 3yr) + market cap per ticker via yfinance, then returns JSON.

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

Owns all UI state (`state` object), tab navigation, ticker chips + autocomplete, portfolio presets (localStorage), view cards (manual + auto signal generator), and the Results page (weight table, bar chart, efficient-frontier canvas scatter, CSV/clipboard export).

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
