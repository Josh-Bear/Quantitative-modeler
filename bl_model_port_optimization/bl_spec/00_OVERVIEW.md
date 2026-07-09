# ML-Driven Black-Litterman Portfolio Optimization
## Project Overview & Specification Index

**Status:** Design locked, ready for implementation
**Last updated:** 2026-06-30
**Target stack:** Python (pandas, numpy, scikit-learn, pytorch/tensorflow)

---

## 1. What This Project Does

Build a quantitative pipeline that:

1. Trains an **LSTM → SVR** model per stock (S&P 500 universe) to predict 63-day forward returns from 8 technical indicators.
2. Uses those predictions to **select 22 stocks** (top 2 per GICS sector × 11 sectors).
3. Constructs **Black-Litterman views (P, Q, Ω)** combining absolute and relative (intra-sector) views from the ML predictions.
4. Runs **Black-Litterman** to get posterior expected returns, then computes the **Efficient Frontier** and a **Max Sharpe portfolio**.
5. **Backtests** the strategy with quarterly rebalancing (rolling 10-year training window, walk-forward), compares against S&P 500 buy-and-hold.

---

## 2. How To Use This Spec (for Claude Code)

This project is split into separate files. **Read and implement them in this order** — each depends on the outputs of the previous one:

| Order | File | Purpose |
|---|---|---|
| 0 | `00_OVERVIEW.md` | This file — read first for context |
| 1 | `01_DATA_PIPELINE.md` | Acquire & prepare all raw data |
| 2 | `02_FEATURE_ENGINEERING.md` | Compute the 8 technical indicators |
| 3 | `03_ML_MODEL.md` | LSTM → SVR training, per-stock, walk-forward |
| 4 | `04_STOCK_SELECTION.md` | Rank stocks, pick 22 (top 2/sector) |
| 5 | `05_BL_MODEL.md` | Construct P, Q, Ω and run Black-Litterman |
| 6 | `06_PORTFOLIO_OPTIMIZATION.md` | Efficient Frontier + Max Sharpe |
| 7 | `07_BACKTEST_ENGINE.md` | Walk-forward backtest loop, costs, rebalancing |
| 8 | `08_EVALUATION_METRICS.md` | Performance metrics, benchmark comparison, reporting |
| 9 | `09_OPEN_DECISIONS.md` | Unresolved items that need a human decision before/during implementation |

Each file is **self-contained**: it restates the inputs it needs and the outputs it must produce, so Claude Code can implement one file mostly independently, then wire modules together using the interfaces defined in each file's "Output Contract" section.

---

## 3. Full Architecture (Visual Reference)

```
┌─────────────────────────────────────────────────────────────┐
│  MODULE 1: DATA PIPELINE                                     │
│  S&P 500 universe, 2010–present, OHLCV + market cap + sector │
└──────────────────────────┬────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  MODULE 2: FEATURE ENGINEERING                                │
│  8 indicators: RSI, ATR, MACD, Keltner, BB, Squeeze,         │
│  Momentum, Hilbert Cycle — 63-day rolling window per stock   │
└──────────────────────────┬────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  MODULE 3: ML MODEL (per stock, ~500 models)                 │
│  [63×8 indicators] → LSTM → hidden state → SVR → r̂ᵢ        │
│  Target: 63-day forward return (direct prediction)            │
│  Retrain: rolling 10-year window, walk-forward at each        │
│  rebalance date                                                │
│  ωᵢ = SVR residual variance on validation set                 │
└──────────────────────────┬────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  MODULE 4: STOCK SELECTION                                     │
│  Rank stocks by r̂ᵢ within each of 11 GICS sectors            │
│  → Select top 2 per sector → 22-stock universe                │
│  (dynamic: re-selected at every rebalance)                     │
└──────────────────────────┬────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  MODULE 5: BLACK-LITTERMAN MODEL                               │
│  Prior: Π = δ·Σ·w_mkt  (22×22, from the 22 selected stocks)   │
│  Views: 22 total = 11 absolute + 11 relative (intra-sector)    │
│  P (22×22), Q (22×1), Ω (22×22, two calibration scales)       │
│  μ_BL = [(τΣ)⁻¹+PᵀΩ⁻¹P]⁻¹[(τΣ)⁻¹Π+PᵀΩ⁻¹Q]                  │
└──────────────────────────┬────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  MODULE 6: PORTFOLIO OPTIMIZATION                               │
│  Efficient Frontier: min wᵀΣw s.t. wᵀμ_BL=r̄, Σw=1            │
│  Max Sharpe point → w*                                          │
└──────────────────────────┬────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  MODULE 7: BACKTEST ENGINE                                     │
│  Walk-forward loop, quarterly rebalance, 0.1%/trade cost       │
│  Re-run modules 3–6 fresh at every rebalance date               │
│  (no look-ahead: only data up to that date is used)             │
└──────────────────────────┬────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  MODULE 8: EVALUATION & REPORTING                               │
│  Return, Sharpe, MDD, Calmar, VaR vs S&P 500 buy & hold        │
│  Turnover stats, ML quality (IC, directional accuracy)          │
└─────────────────────────────────────────────────────────────┘
```

---

## 4. Locked Design Decisions (Reference Table)

These were debated and finalized across the design discussion. **Do not silently change these** — if Claude Code believes one should change, it must flag it explicitly rather than substitute its own choice.

| Component | Decision |
|---|---|
| Universe (ML training) | S&P 500, ~500 stocks |
| Indicators (8) | RSI, ATR, MACD, Keltner Channel, Bollinger Bands, Squeeze (on/off), Momentum, Hilbert Transform Cycle |
| Input window | 63 trading days (1:1 with the 63-day prediction horizon — see `03_ML_MODEL.md` §2) |
| ML architecture | LSTM (sequence encoder) → SVR (RBF kernel, regressor) |
| Training granularity | 1 LSTM+SVR pair per stock (not shared across stocks) |
| Prediction target | 63-trading-day forward return, predicted directly (not via intermediate indicator forecasting) |
| Retrain strategy | Rolling window, fixed size = 10 years, walk-forward at every rebalance |
| Stock selection | Top 2 stocks per GICS sector, ranked by SVR-predicted return → 22-stock universe, re-selected every rebalance |
| BL universe | Only the 22 selected stocks (not all 500) |
| View structure | Mixed: 11 absolute views (one per sector's top stock) + 11 relative views (top vs. 2nd stock within each sector) = 22 views total |
| Q (view returns) | Absolute view: Q = r̂ᵢ. Relative view: Q = r̂_top,s − r̂_2nd,s |
| Ω (view uncertainty) | Diagonal matrix from SVR validation-set residual variance, calibrated with two separate scale factors (absolute vs. relative) so both are on the same order of magnitude as τΣ |
| τ (tau) | 0.05 |
| δ (risk aversion) | 2.5 |
| Optimization | Full Efficient Frontier (for visualization) + Max Sharpe portfolio (for backtest) |
| Rebalance frequency | Every 3 months (quarterly) |
| Transaction cost | 0.1% per trade, applied to turnover |
| Backtest performance window | Only the designated backtest period counts toward reported metrics; the training window before it is used only to fit models/estimate Σ, never counted as performance |
| Benchmark | S&P 500 index, buy & hold |
| Data history | 2010 to present |
| Data source | yfinance (or equivalent free API) — **no data pipeline exists yet, must be built from scratch** |

---

## 5. Critical Constraints That Must Be Respected Throughout

These are correctness requirements that affect multiple modules. Flag in code comments wherever they apply:

1. **No look-ahead bias.** At any rebalance date `t`, every computation (indicator values, model training, Σ estimation, stock ranking) must use only data with timestamp `< t`. This applies inside the rolling 10-year window too — the window itself must end before `t`.

2. **Walk-forward retraining.** The LSTM+SVR models are NOT trained once. They are retrained at every rebalance date using the most recent rolling 10-year window ending just before that date. This is computationally expensive — the backtest engine should be designed to make this tractable (see `07_BACKTEST_ENGINE.md` for caching/parallelization notes).

3. **Time-series splits only.** Train/validation splits for SVR residual variance (used for Ω) must be chronological, never random shuffling.

4. **Survivorship bias is an open, unresolved limitation.** See `09_OPEN_DECISIONS.md`. Default behavior: use the current S&P 500 list applied retroactively, and explicitly log this as a limitation in the final report. Do not attempt to silently "fix" this without flagging it.

5. **Scale consistency in Ω.** Absolute-view uncertainty and relative-view uncertainty are calibrated with separate scale factors. Never use a single global scale factor for both — this was explicitly decided against.

6. **22-stock universe is dynamic.** The specific 22 tickers can (and likely will) change at every rebalance date, since they're re-selected by SVR ranking each time. The backtest must handle stocks entering/leaving the portfolio and charge transaction costs accordingly.

---

## 6. What "Done" Looks Like

The final deliverable is a backtest report containing:

- Cumulative return curve: strategy vs. S&P 500 buy & hold
- Efficient Frontier plot at one or more representative rebalance dates
- Table: Annualized Return, Sharpe Ratio, Max Drawdown, Calmar Ratio, VaR/CVaR — strategy vs. benchmark
- Turnover statistics per rebalance
- ML model quality diagnostics: Information Coefficient (IC) per sector, directional accuracy
- Explicit limitations section: survivorship bias, rolling-window crisis coverage, transaction cost assumptions

See `08_EVALUATION_METRICS.md` for exact definitions and `09_OPEN_DECISIONS.md` for known gaps to disclose.
