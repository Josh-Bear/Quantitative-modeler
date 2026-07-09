# Module 9: Open Decisions Log

This file lists every point in the design that was **explicitly flagged as unresolved, approximated, or requiring a judgment call** during the design discussion. Claude Code should NOT silently resolve these by picking whatever is easiest to implement — each one should either:

(a) be implemented using the **documented default** below, with a clear code comment noting it's a documented simplification, or
(b) be flagged back to the user with a specific question if the default seems to be causing problems during implementation (e.g., poor data quality, infeasible runtime, clearly wrong results).

---

## 1. Survivorship Bias

**Issue:** Using today's S&P 500 constituent list applied retroactively to 2010 excludes historically-delisted/acquired companies and includes recent additions that weren't in the index for the full backtest period.

**Default:** Accept this as a known limitation. Use the current constituent list (Module 1, Section 3.1) for the entire backtest. Disclose explicitly in the final report (Module 8, Section 7).

**Revisit if:** the user gains access to a point-in-time historical constituents data source (e.g., a paid provider). This was explicitly decided as out-of-scope for this iteration of the project.

---

## 2. Historical Market Cap Reconstruction

**Issue:** yfinance does not provide historical market cap directly; it must be approximated as `shares_outstanding × historical_price`, assuming shares outstanding is roughly constant — an approximation that degrades over a full decade due to buybacks/share issuance.

**Default:** Attempt Option A (reconstruction) from `01_DATA_PIPELINE.md` Section 3.3. If data quality issues arise for many tickers, fall back to Option B (static current market cap used throughout) and log which tickers used the fallback.

**Revisit if:** the fallback ends up being used for more than ~20% of tickers — at that point, the mcap-weighting in Module 5 may be meaningfully distorted and worth flagging back to the user.

---

## 3. Sector Classification Held Fixed

**Issue:** GICS sector assignments can change over time (companies get reclassified); this project uses a single, current snapshot for the entire 2010-present backtest.

**Default:** Accept as a simplification. Disclose in the final report.

**Revisit if:** specific large/well-known reclassifications materially affect results in a way worth investigating (e.g., a stock that moved from Industrials to Information Technology mid-backtest) — this is unlikely to be worth the engineering effort unless results look suspicious for a specific sector.

---

## 4. SVR Hyperparameter Tuning Granularity

**Issue:** Tuning `C` and `epsilon` separately for all ~500 stocks at every rebalance date is computationally expensive and may overfit small per-stock validation sets.

**Default:** Tune once on a representative sample of 20-30 liquid, sector-diverse stocks (per `03_ML_MODEL.md` Section 5), apply the same (C, epsilon) uniformly across all stocks and all rebalance dates.

**Revisit if:** SVR performance (validation R² or IC, per Module 8 Section 4) looks poor for specific sectors — consider per-sector tuning as a middle-ground compromise before going to full per-stock tuning.

---

## 5. LSTM Training Approach (Option A vs. Option B)

**Issue:** Two ways to get useful hidden states from the LSTM — train it directly as a regressor with a linear head (Option A), or train it as a sequence autoencoder (Option B).

**Default:** Option A (per `03_ML_MODEL.md` Section 4.3) — simpler, standard, defensible.

**Revisit if:** downstream SVR performance is unsatisfactory after using Option A's hidden states — only then consider the added complexity of Option B.

---

## 6. Long-Only vs. Long-Short Portfolio Constraint

**Issue:** The BL views include relative (long-short flavored) comparisons within sectors, but the final portfolio optimization could still be either long-only or allow shorting.

**Default:** Long-only (per `06_PORTFOLIO_OPTIMIZATION.md` Section 3) — standard for an equity portfolio backtest, and the relative views inform μ_BL without requiring the portfolio itself to short anything.

**Revisit if:** the user explicitly wants to express the sector relative views as actual long/short positions in the final portfolio — this is a meaningfully different strategy (market-neutral-ish vs. long-only) and should be a deliberate choice, not a default.

---

## 7. Transaction Cost Approximation

**Issue:** Charging cost on full turnover (every weight change, including minor adjustments to stocks held in both periods) vs. a simplified version (cost only on stocks fully entering/exiting the 22-stock universe).

**Default:** Full turnover version (per `07_BACKTEST_ENGINE.md` Section 6) — more accurate, not meaningfully harder to implement.

**Revisit if:** never, unless profiling shows this is a performance bottleneck (extremely unlikely given the small portfolio size of 22 stocks).

---

## 8. Backtest Start Date

**Issue:** `BACKTEST_START` (the date after which returns count as "performance," per `07_BACKTEST_ENGINE.md` Section 2) needs to be set far enough after 2010 to allow a full 10-year rolling training window for the first rebalance date.

**Default:** Not yet set to a specific value — this requires a decision based on how much performance-period data is desired vs. how much history is available. Minimum valid value: `2010-01-01 + 10 years = 2020-01-01`. Recommend setting `BACKTEST_START = 2020-01-01` or later, giving at least several years of out-of-sample performance period given the current date (2026).

**This must be explicitly set before Module 7 can run** — it is the one true "must decide before coding" item that doesn't yet have a default in this spec; everything else has a documented fallback.

---

## 9. SP500 Sector Count Validation

**Issue:** The design assumes exactly 11 GICS Level-1 sectors will each have at least 2 viable stocks at every rebalance date. This is very likely true for S&P 500 broadly, but should be validated rather than assumed.

**Default:** Implement the edge-case handling in `04_STOCK_SELECTION.md` Section 3 (sectors with <2 candidates degrade gracefully). Run a quick check early in development: confirm all 11 sectors are present in the data with reasonable stock counts (Module 1's sector mapping output).

**Revisit if:** any sector consistently has very few stocks (e.g., Real Estate, Utilities sometimes have fewer S&P 500 constituents than other sectors) — confirm the edge-case handling is actually triggering correctly rather than silently producing a smaller universe every single rebalance.

---

## 10. Risk-Free Rate Source

**Issue:** Sharpe ratio (Module 8, Section 2) and Max Sharpe optimization (Module 6, Section 4) both need a risk-free rate input, which hasn't been explicitly sourced yet.

**Default:** Use 0% as a placeholder if no source is readily available, OR pull 3-month T-bill rates from FRED (free API, `fredapi` Python package, series `DTB3`) if internet access allows — recommended since it's low-effort and more realistic than a flat 0%.

**Revisit if:** the choice of risk-free rate meaningfully changes the Sharpe ratio conclusions (unlikely to matter much given typical equity strategy return magnitudes, but cheap to get right).

---

## 11. Universe Narrowed to S&P 100; Selection Ranking Made Risk-Adjusted

**Status:** Not a documented default resolved during original design — these are
**explicit deviations from `00_OVERVIEW.md` §4's locked decisions**, requested and
approved by Josh on 2026-07-02 after reviewing an actual `--full` run and its
output. Recorded here per this file's own convention (§9's advice: surface back to
the user when a default is "causing problems during implementation" — here the
locked decision itself, not a default, was the problem).

**11a. Universe: S&P 500 → S&P 100 for `--full`.**
Issue: 00 §4 locks the ML-training universe to "S&P 500, ~500 stocks." A real
`--full` run (500 stocks × 26 quarterly rebalances, `n_jobs=8`) was executed on
2026-07-01/02 and reached only 15/26 rebalance dates before being manually
interrupted (`KeyboardInterrupt` in `nohup.out`); per-rebalance training alone took
~40-45 minutes even parallelised across 8 workers, implying a full run is
realistically 15-20+ hours end to end. That is not tractable to iterate on.
Decision: `data_pipeline.get_universe(universe=None)` (the path `--full` uses) now
fetches the **S&P 100** constituent list from Wikipedia (`constants.WIKI_SP100_URL`)
instead of the S&P 500. `--quick`/`--default` are unaffected (they already pass a
small fixed `universe` list). Trade-off to keep in mind: S&P 100 has ~9 candidates
per GICS sector on average (vs ~45 for S&P 500), so top-2/sector selection has less
room to differentiate within thin sectors (Real Estate, Utilities, Materials,
Energy) — watch `[M4] sector '...' has only N candidate` warnings if reviving the
S&P 500 scope later.

**11b. Stock selection: raw r_hat ranking → risk-adjusted score.**
Issue: `04_STOCK_SELECTION.md` §2 ranks candidates within each sector by raw
`r_hat` (the SVR point estimate) and cuts at rank 2. This project's own ML-quality
diagnostics (`08_EVALUATION_METRICS.md` §4.1, computed by `evaluation.ml_diagnostics`)
measured mean IC ≈ 0.086 on an actual run — "weakly predictive" by the spec's own
stated threshold (IC > 0.05). Ranking noisy point estimates by their raw value and
making a hard cut at rank 2 lets estimation noise, not genuine predictive skill,
decide which stocks enter the 22-stock universe — and therefore the BL views.
Decision: `selection.select_universe` now ranks by `score = r_hat / sqrt(omega)`
(a t-stat-like measure; `omega` floored at `OMEGA_FLOOR = 1e-8` to avoid division
by a near-zero validation residual variance). A high `r_hat` backed by a noisy
(high-`omega`) prediction is discounted relative to a smaller `r_hat` the model is
confident about. **Q, the view return M5 feeds into Black-Litterman, is still the
raw `r_hat`** — only the selection/ranking criterion changed, not the economic
content of the views. Verified in `test.py::test_selection` with a case where the
risk-adjusted ranking provably flips the raw-r_hat order.

**Revisit if:** S&P 100's thinner per-sector candidate pool (11a) causes the
`<2 candidates` edge case (04 §3.1) to trigger often — that's a sign the universe
is now too narrow for reliable sector coverage and either the sector-count
threshold or the universe scope needs revisiting. For 11b, if downstream backtest
Sharpe/turnover doesn't improve versus the raw-r_hat baseline, the shrinkage
strength implicit in `1/sqrt(omega)` could be tempered (e.g. a partial exponent)
rather than assumed correct by construction.

---

## How to Use This File During Implementation

When Claude Code encounters any of the above situations, it should implement the **Default** behavior, add a code comment referencing this file and section number (e.g., `# See 09_OPEN_DECISIONS.md, Section 4 — tuned once on a sample, not per-stock`), and only surface a question back to the user if the "Revisit if" condition is actually triggered during a real run.
