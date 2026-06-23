# CLAUDE.md

Guidance for Claude Code when working in `bl_lstm_views/`.

## What this is

The ML **investor's-view generator** for Black-Litterman: a Python pipeline that forecasts
stock returns (LSTM→SVR) and turns them into the BL view vector Q + uncertainty Ω, then
optimises and backtests. Sibling to `black_litterman_model/` (the JS web app that does BL
math interactively); this directory produces `output/views.json` in that app's
`BL.compute()` input shape.

## Running

```bash
pip install -r requirements.txt
python run.py --quick      # smoke (2 stocks, 3 epochs)
python run.py              # default (~6 stocks)
python run.py --full       # paper scope (slow)
python test.py             # network-free BL-core checks
```

## Architecture

```
run.py                 # orchestrates fetch → indicators → train → views → BL → backtest; prints summary + QA
src/constants.py       # ALL config; resolve_profile() maps --quick/--full to (universe, epochs)
src/fetch_data.py      # yfinance daily OHLCV + market caps; caches to output/cache/, falls back to it
src/indicators.py      # the 8 features in PURE pandas/numpy (no pandas_ta / TA-Lib)
src/preprocessing.py   # train-only MinMax, 30-day windows, 5-day-ahead targets, index bookkeeping
src/lstm_model.py      # PyTorch 4×60 LSTM; one model per indicator (8/stock); MPS→CUDA→CPU
src/svr_model.py       # sklearn SVR(RBF,C=5,ε=0.01): scaled indicators → scaled close
src/views.py           # composes LSTM+SVR → Q (annualised) + Ω (from test error); writes views.json
src/black_litterman.py # numpy BL: Π, μ_BL, w*, constraints (ports zzz.py + JS engine policy)
src/backtest.py        # rolling 5-day rebalance vs SPY; annual return / Sharpe / max drawdown
```

## Key design decisions (don't "fix" these without reading)

- **Indicators are pure pandas/numpy by choice.** No `pandas_ta`/TA-Lib. `hilbert` is an
  FFT dominant-cycle approximation of TA-Lib's `HT_DCPERIOD`.
- **SVR is contemporaneous** (indicators(d)→close(d)). The forecast horizon comes entirely
  from the LSTM predicting indicators HORIZON days ahead; SVR only decodes indicators→price.
  Don't shift the SVR target — that would double-count the horizon.
- **Scaler fit on the train slice only** (`preprocessing.build_stock_dataset`). Never refit
  on val/test — that leaks the future.
- **Window index bookkeeping**: every sample carries `asof_idx` (day you stand on) and
  `target_idx = asof_idx + HORIZON` (day forecast). views.py and backtest.py rely on these
  to line predictions up with realised prices.
- **Annualisation is linear** (×TRADING_DAYS/HORIZON) for view returns; Ω ×factor². Keeps Q
  in the same units as the annualised prior Π without explosive compounding.
- **BL constraints mirror the JS engine**: long-only clamp → normalise → per-asset cap via
  iterative water-filling; `DIAG_EPS=1e-4` before inversion; **no views ⇒ w*=w_mkt** (the
  identity `test.py` asserts).

## Caveat to keep stating

Runnable research scaffold, **not** a profitable strategy. MinMax on trending features
(OBV, band widths) can exceed [0,1] on val/test; backtest numbers are illustrative.
