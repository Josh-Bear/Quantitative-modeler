# CLAUDE.md

Guidance for Claude Code when working in `bl_model_port_optimization/`.

## What this is

An ML-driven **Black-Litterman portfolio optimiser with a walk-forward backtest**.
A per-stock LSTM→SVR forecasts 63-day forward returns over the S&P 500, the top-2
stocks per GICS sector form a dynamic 22-stock universe, Black-Litterman turns the
forecasts into a posterior μ_BL (11 absolute + 11 relative views), mean-variance
optimisation picks the Max-Sharpe portfolio, and the whole thing is backtested
quarterly vs S&P 500 buy-&-hold.

The full design spec lives in `bl_spec/` (`00_OVERVIEW.md` … `09_OPEN_DECISIONS.md`).
**Read the spec before changing behaviour.** `00 §4` is the locked-decision table
(do not silently change); `09` is the open-decision log with documented defaults —
each default is referenced in code as `# 09 §N`.

## Running

```bash
pip install -r requirements.txt          # incl. TA-Lib (brew install ta-lib first)
python run.py --quick                     # smoke: 22 stocks, 2 rebalances, 5 epochs
python run.py                             # default: ~44 stocks, 4 rebalances, 30 epochs
python run.py --full                      # live S&P 500, full quarterly schedule (slow)
python run.py --jobs 8                     # fan per-stock training across CPU workers
python test.py                            # network-free core checks (BL / opt / metrics)
```

Uses the repo-root `.venv` (Python 3.14: numpy, pandas, scipy, sklearn, torch,
yfinance, talib, pyarrow, lxml, fredapi, matplotlib). **TA-Lib is the only external
indicator library** (HT_DCPERIOD); every other indicator is hand-rolled in pure
pandas/numpy, so a missing `ta`/`pandas-ta` can't break feature engineering.
`features.check_indicator_deps()` fails fast with a clear message if TA-Lib is
absent (it previously degraded to a silent per-ticker mass-skip).

> Run with `.venv/bin/python` (or activate it). A different interpreter that lacks
> these packages is the usual cause of `No module named …` mid-run.

## Architecture (modules map 1:1 to the spec)

```
run.py                  # orchestrate M1→M8; profiles; summary + QA
src/constants.py        # ALL config — locked decisions (00 §4) + 09 defaults; resolve_profile()
src/data_pipeline.py    # M1: S&P500 list (Wikipedia), yfinance OHLCV→parquet, mcap A→B, sector map, QA
src/features.py         # M2: 8 indicators (pure pandas/numpy + TA-Lib Hilbert only); raw, warm-up dropped
src/ml_model.py         # M3: per-stock LSTM extractor (Option A) → SVR; ω from val residuals; walk-forward
src/selection.py        # M4: top-2/sector → 22-stock universe; turnover
src/black_litterman.py  # M5: Σ(×63) → P,Q (block) → Ω (two scales) → Π → μ_BL
src/optimization.py     # M6: efficient frontier + Max-Sharpe (long-only); closed-form sanity check
src/backtest.py         # M7: quarterly walk-forward loop, costs, caching, risk-free; calls M3-M6
src/evaluation.py       # M8: metrics vs SPY, IC/dir-accuracy/RMSE, turnover, crisis coverage, report
```

Data/outputs land under `data/` (raw prices, features, reference) and `output/`
(predictions, universe, bl_outputs, portfolios, backtest_results, report).

## Key design decisions (don't "fix" without reading the spec)

- **Architecture A (09 §5)**: the LSTM is a *feature extractor*. It is trained
  end-to-end with a linear head (MSE) on the 63-day target, then the head is
  discarded and the final hidden state feeds the SVR, which predicts the 63-day
  return **directly** (not via forecasting indicators ahead — that's the *sibling*
  `bl_lstm_views`, a different design). Don't shift the SVR target.
- **No look-ahead (00 §5.1)** is enforced in `ml_model.build_training_data`: the
  feature slice is strictly `< reb_date`, and any 63-day target whose forward
  close would land on/after `reb_date` is dropped. Σ uses the *same* rolling
  10-year window (05 §3).
- **Per-window z-scoring fit on the train slice only** (02 §4.2). The scaler is fit
  on feature rows up to the last training as-of position, never on val/the
  prediction window.
- **Unit consistency (05 §7)**: Σ is built from daily returns then scaled `×63`
  ONCE (`HORIZON_SCALE`) so it matches the 63-day Q/Π. The risk-free rate is
  converted to 63-day units in M6. Mixing daily-Σ with 63-day-Q is the classic
  silent bug — don't.
- **Two-scale Ω (00 §4, 05 §5)**: absolute and relative views are calibrated with
  **separate** scale factors (`alpha_abs`, `alpha_rel`). Never a single global
  scale — explicitly decided against. Views are **block-ordered** (all absolute
  first, then relative) because `construct_omega`'s masks rely on it.
- **τ=0.05, δ=2.5 fixed** (00 §4). `BACKTEST_START=2020-01-01` (09 §8, user-set) —
  the first date whose realised returns count as performance; pre-2020 data only
  feeds rolling windows.
- **SVR tuned once** on a ~20-stock sample, applied uniformly (09 §4). Quick
  profile skips tuning (placeholder C=5, ε=0.01).
- **Long-only** Max-Sharpe (09 §6); transaction cost on **full turnover** (09 §7);
  quarterly rebalance → `periods_per_year=4` for annualisation (08 §2).
- **Skip-and-continue**: any ticker that fails to fetch / lacks history / blows up
  in training is dropped with a warning; OOM is re-raised so callers can react.
  Per-date M3 predictions are cached to `output/predictions/{date}.parquet`.

## Caveats to keep stating

Research scaffold, **not** a profitable strategy. Known limitations are disclosed
in the generated report (08 §7): survivorship bias (current S&P 500 applied
retroactively), rolling-window crisis coverage gaps, mcap reconstruction
approximation, fixed sector classification, and overlapping-target autocorrelation
shrinking the effective sample size.
```
