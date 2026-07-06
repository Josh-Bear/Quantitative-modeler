"""
Module 8: Evaluation Metrics & Reporting (bl_spec/08_EVALUATION_METRICS.md)

Performance + risk metrics on the backtest's realised returns, an apples-to-apples
S&P 500 buy-&-hold comparison, ML-quality diagnostics (IC, directional accuracy,
RMSE per sector), turnover/cost analysis, crisis-coverage disclosure, and a
markdown report with figures.

All performance metrics are restricted to the performance period (08 §2) and use
periods_per_year = 4 (quarterly holding periods — NOT 252 or 12).
"""
from __future__ import annotations

import os
import warnings
from typing import Optional

import numpy as np
import pandas as pd

from . import constants as C
from . import data_pipeline as dp

PPY = C.PERIODS_PER_YEAR


# ─────────────────────────────────────────────────────────────────────────────
# 2. Return & risk metrics  (08 §2)
# ─────────────────────────────────────────────────────────────────────────────
def annualized_return(r: pd.Series, ppy: int = PPY) -> float:
    cumulative = (1 + r).prod()
    n_years = len(r) / ppy
    return cumulative ** (1 / n_years) - 1 if n_years > 0 else np.nan


def annualized_volatility(r: pd.Series, ppy: int = PPY) -> float:
    return r.std() * np.sqrt(ppy)


def sharpe_ratio(r: pd.Series, rf_annual: float = 0.0, ppy: int = PPY) -> float:
    excess = r - rf_annual / ppy
    return (excess.mean() / excess.std()) * np.sqrt(ppy) if excess.std() > 0 else np.nan


def max_drawdown(portfolio_value: pd.Series) -> float:
    running_max = portfolio_value.cummax()
    return ((portfolio_value - running_max) / running_max).min()


def calmar_ratio(r: pd.Series, pv: pd.Series, ppy: int = PPY) -> float:
    mdd = abs(max_drawdown(pv))
    return annualized_return(r, ppy) / mdd if mdd > 0 else np.nan


def value_at_risk(r: pd.Series, confidence: float = 0.95) -> float:
    return r.quantile(1 - confidence)


def conditional_var(r: pd.Series, confidence: float = 0.95) -> float:
    var = value_at_risk(r, confidence)
    tail = r[r <= var]
    return tail.mean() if len(tail) else np.nan


def metric_table(r: pd.Series, pv: pd.Series, rf_annual: float = 0.0) -> dict:
    return {
        "Annualized Return": annualized_return(r),
        "Annualized Volatility": annualized_volatility(r),
        "Sharpe Ratio": sharpe_ratio(r, rf_annual),
        "Max Drawdown": max_drawdown(pv),
        "Calmar Ratio": calmar_ratio(r, pv),
        "VaR (95%)": value_at_risk(r),
        "CVaR (95%)": conditional_var(r),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 3. Benchmark — S&P 500 buy-&-hold over the SAME holding periods  (08 §3)
# ─────────────────────────────────────────────────────────────────────────────
def benchmark_series(periods: list[tuple]) -> pd.Series:
    """S&P 500 buy-&-hold return over each (start, end) interval — the SAME
    holding periods the strategy used, so Sharpe/MDD/etc. compare apples to
    apples (08 §3)."""
    import yfinance as yf
    try:
        px = yf.download(C.BENCHMARK, start=C.BACKTEST_START, end=None,
                         auto_adjust=True, progress=False)["Close"]
        if isinstance(px, pd.DataFrame):
            px = px.iloc[:, 0]
    except Exception as e:  # noqa: BLE001
        warnings.warn(f"[M8] benchmark download failed: {e}")
        return pd.Series(dtype=float)

    out = {}
    for start, end in periods:
        p0, p1 = px.asof(pd.Timestamp(start)), px.asof(pd.Timestamp(end))
        if p0 and p1 and p0 > 0:
            out[pd.Timestamp(start)] = p1 / p0 - 1.0
    return pd.Series(out)


# ─────────────────────────────────────────────────────────────────────────────
# 4. ML-quality diagnostics  (08 §4)
# ─────────────────────────────────────────────────────────────────────────────
def realized_forward_returns(tickers: list[str], reb_date) -> pd.DataFrame:
    """The actual 63-day return that FOLLOWED a rebalance date (hindsight, for
    diagnostics only)."""
    reb_ts = pd.Timestamp(reb_date)
    rows = []
    for t in tickers:
        s = dp.load_close_series(t)
        if s is None:
            continue
        fwd = s[s.index >= reb_ts]
        if len(fwd) > C.HORIZON:
            rows.append({"ticker": t,
                         "actual_63day_return": float(fwd.iloc[C.HORIZON] / fwd.iloc[0] - 1)})
    return pd.DataFrame(rows)


def ml_diagnostics(sector_map: dict) -> dict:
    """Mean IC, directional accuracy, and per-sector breakdowns across all cached
    rebalance dates, over the FULL universe (before selection bias) (08 §4)."""
    from scipy.stats import spearmanr
    pred_files = sorted(f for f in os.listdir(C.PREDICTIONS_DIR) if f.endswith(".parquet")) \
        if os.path.isdir(C.PREDICTIONS_DIR) else []

    ics, das, merged_all = [], [], []
    for f in pred_files:
        reb = f[:-8]
        preds = pd.read_parquet(os.path.join(C.PREDICTIONS_DIR, f))
        actuals = realized_forward_returns(preds["ticker"].tolist(), reb)
        if actuals.empty:
            continue  # most-recent rebalance(s) have no realised 63-day forward yet
        m = preds.merge(actuals, on="ticker")
        if len(m) < 3:
            continue
        ic, _ = spearmanr(m["r_hat"], m["actual_63day_return"])
        da = float((np.sign(m["r_hat"]) == np.sign(m["actual_63day_return"])).mean())
        ics.append(ic); das.append(da)
        m["sector"] = m["ticker"].map(sector_map)
        merged_all.append(m)

    if not merged_all:
        return {"mean_ic": np.nan, "mean_directional_accuracy": np.nan,
                "ic_by_sector": pd.DataFrame(), "rmse_by_sector": pd.DataFrame()}

    allm = pd.concat(merged_all, ignore_index=True)

    def sector_ic(g):
        return spearmanr(g["r_hat"], g["actual_63day_return"])[0] if len(g) > 2 else np.nan
    ic_by_sector = allm.groupby("sector").apply(sector_ic, include_groups=False)
    allm["sq_err"] = (allm["r_hat"] - allm["actual_63day_return"]) ** 2
    rmse_by_sector = allm.groupby("sector")["sq_err"].apply(lambda x: np.sqrt(x.mean()))

    return {
        "mean_ic": float(np.mean(ics)),
        "mean_directional_accuracy": float(np.mean(das)),
        "ic_by_sector": ic_by_sector.rename("ic").reset_index(),
        "rmse_by_sector": rmse_by_sector.rename("rmse").reset_index(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 6. Rolling-window crisis coverage  (08 §6)
# ─────────────────────────────────────────────────────────────────────────────
def crisis_coverage(rebalance_dates: list) -> pd.DataFrame:
    rows = []
    for d in rebalance_dates:
        window_start = pd.Timestamp(d) - pd.DateOffset(years=C.ROLLING_WINDOW_YEARS)
        visible = [name for name, start, _ in C.KNOWN_CRISES
                   if pd.Timestamp(start) >= window_start]
        rows.append({"rebalance_date": pd.Timestamp(d).date().isoformat(),
                     "crises_in_training_window": ", ".join(visible) if visible else "none"})
    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────────────
# Figures + report
# ─────────────────────────────────────────────────────────────────────────────
def _fig_dir() -> str:
    d = os.path.join(C.REPORT_DIR, "figures"); os.makedirs(d, exist_ok=True); return d


def plot_cumulative(results: pd.DataFrame, bench: pd.Series) -> str:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(results["date"], results["portfolio_value"], label="Strategy", lw=2)
    if not bench.empty:
        bench_pv = (1 + bench).cumprod()
        ax.plot(bench_pv.index, bench_pv.values, label="S&P 500 (B&H)", lw=2, ls="--")
    ax.set_title("Cumulative return: strategy vs S&P 500")
    ax.set_ylabel("Normalised value"); ax.legend(); ax.grid(alpha=0.3)
    path = os.path.join(_fig_dir(), "cumulative_return.png")
    fig.tight_layout(); fig.savefig(path, dpi=110); plt.close(fig)
    return path


def plot_frontier(reb_key: str) -> Optional[str]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fpath = os.path.join(C.PORTFOLIO_DIR, f"{reb_key}_frontier.parquet")
    ppath = os.path.join(C.PORTFOLIO_DIR, f"{reb_key}.npz")
    if not os.path.exists(fpath):
        return None
    fr = pd.read_parquet(fpath)
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.plot(fr["volatility"], fr["target_return"], "-o", ms=3, label="Efficient frontier")
    if os.path.exists(ppath):
        z = np.load(ppath, allow_pickle=True)
        bl_npz = os.path.join(C.BL_DIR, f"{reb_key}.npz")
        if os.path.exists(bl_npz):
            b = np.load(bl_npz)
            w = z["w_star"]
            ax.plot(np.sqrt(w @ b["Sigma"] @ w), w @ b["mu_BL"], "r*", ms=16, label="Max Sharpe")
    ax.set_xlabel("Volatility (63-day)"); ax.set_ylabel("Expected return (63-day)")
    ax.set_title(f"Efficient frontier @ {reb_key}"); ax.legend(); ax.grid(alpha=0.3)
    path = os.path.join(_fig_dir(), f"efficient_frontier_{reb_key}.png")
    fig.tight_layout(); fig.savefig(path, dpi=110); plt.close(fig)
    return path


def plot_turnover(turnover_log: pd.DataFrame) -> Optional[str]:
    if turnover_log.empty:
        return None
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(9, 4))
    changed = 1 - turnover_log["overlap_pct"].fillna(0)
    ax.bar(range(len(turnover_log)), changed * 100)
    ax.set_xticks(range(len(turnover_log)))
    ax.set_xticklabels(turnover_log["date"].astype(str).str[:10], rotation=45, ha="right", fontsize=7)
    ax.set_ylabel("% universe changed"); ax.set_title("Universe turnover per rebalance")
    ax.grid(alpha=0.3, axis="y")
    path = os.path.join(_fig_dir(), "turnover_over_time.png")
    fig.tight_layout(); fig.savefig(path, dpi=110); plt.close(fig)
    return path


def _fmt(table: dict) -> str:
    def pct(k, v):
        return f"{v:.2%}" if "Ratio" not in k else f"{v:.3f}"
    return "\n".join(f"| {k} | {pct(k, v)} |" for k, v in table.items())


# ─────────────────────────────────────────────────────────────────────────────
# Holdings by rebalance + period-by-period vs S&P 500 (Josh, 2026-07-02 request —
# extends the 08 §7 report structure; not a spec-mandated section)
# ─────────────────────────────────────────────────────────────────────────────
def holdings_table() -> pd.DataFrame:
    """Every holding at every rebalance: [date, ticker, weight, sector, r_hat,
    rank_in_sector]. Reads `backtest_results/weights_history.parquet` (M7) and
    enriches each date's rows from `universe/{date}.parquet` (M4) where present.
    Sorted by date then weight descending. Empty DataFrame if no backtest has run."""
    wpath = os.path.join(C.BACKTEST_DIR, "weights_history.parquet")
    if not os.path.exists(wpath):
        return pd.DataFrame()
    w = pd.read_parquet(wpath)
    w["date"] = pd.to_datetime(w["date"])

    rows = []
    for d, grp in w.groupby("date", sort=True):
        key = d.date().isoformat()
        upath = os.path.join(C.UNIVERSE_DIR, f"{key}.parquet")
        if os.path.exists(upath):
            extra = pd.read_parquet(upath)[["ticker", "sector", "r_hat", "rank_in_sector"]]
            g = grp.merge(extra, on="ticker", how="left")
        else:
            g = grp.copy()
        rows.append(g)
    out = pd.concat(rows, ignore_index=True)
    return out.sort_values(["date", "weight"], ascending=[True, False]).reset_index(drop=True)


def period_comparison_table(results: pd.DataFrame, bench: pd.Series) -> pd.DataFrame:
    """Strategy vs S&P 500 return for EVERY individual rebalance period (not just
    the single aggregate row in the performance-comparison table) — same
    (date, period_end) holding window per row, so each line is apples-to-apples.
    `bench` is the Series from `benchmark_series()`, indexed by period start date."""
    cols = ["date", "period_end", "period_return", "portfolio_value"]
    r = results[[c for c in cols if c in results.columns]].copy()
    r["date"] = pd.to_datetime(r["date"])
    r["sp500_return"] = r["date"].map(bench)
    r["sp500_value"] = (1 + r["sp500_return"].fillna(0.0)).cumprod()
    r["active_return"] = r["period_return"] - r["sp500_return"]
    return r[["date", "period_end", "period_return", "sp500_return",
              "active_return", "portfolio_value", "sp500_value"]]


def _holdings_md(holdings: pd.DataFrame, reb_date) -> str:
    """Markdown table of every holding on one rebalance date."""
    sub = holdings[holdings["date"] == pd.Timestamp(reb_date)]
    if sub.empty:
        return "_(no holdings recorded for this date)_\n"
    lines = ["| Ticker | Sector | Weight | r_hat | Rank in sector |",
             "|---|---|---|---|---|"]
    for _, row in sub.iterrows():
        sector = row["sector"] if pd.notna(row.get("sector")) else "-"
        r_hat = f"{row['r_hat']:.2%}" if pd.notna(row.get("r_hat")) else "-"
        rank = int(row["rank_in_sector"]) if pd.notna(row.get("rank_in_sector")) else "-"
        lines.append(f"| {row['ticker']} | {sector} | {row['weight']:.2%} | {r_hat} | {rank} |")
    return "\n".join(lines)


def _period_cmp_md(period_cmp: pd.DataFrame) -> str:
    """Markdown table: strategy vs S&P 500 return for every rebalance period."""
    lines = ["| Rebalance | Period end | Strategy | S&P 500 (B&H) | Active |",
             "|---|---|---|---|---|"]
    for _, row in period_cmp.iterrows():
        sp = f"{row['sp500_return']:.2%}" if pd.notna(row["sp500_return"]) else "n/a"
        act = f"{row['active_return']:+.2%}" if pd.notna(row["active_return"]) else "n/a"
        lines.append(f"| {row['date'].date()} | {row['period_end'].date()} | "
                     f"{row['period_return']:+.2%} | {sp} | {act} |")
    return "\n".join(lines)


def generate_report(results: pd.DataFrame, sector_map: dict,
                    rebalance_dates: list, rf_annual: float = 0.0,
                    limitations: Optional[list[str]] = None) -> str:
    """Compile the full markdown report + figures + CSV tables (08 §7, §8)."""
    os.makedirs(os.path.join(C.REPORT_DIR, "tables"), exist_ok=True)
    tdir = os.path.join(C.REPORT_DIR, "tables")

    r = results.set_index("date")["period_return"]
    pv = results.set_index("date")["portfolio_value"]
    strat = metric_table(r, pv, rf_annual)

    # benchmark over the strategy's exact (start, end) holding intervals
    if "period_end" in results.columns:
        periods = list(zip(results["date"], results["period_end"]))
    else:  # backward-compat: consecutive rebalance dates
        bounds = list(rebalance_dates) + [pd.Timestamp(C.BACKTEST_END)]
        periods = list(zip(bounds[:-1], bounds[1:]))
    bench = benchmark_series(periods)
    if not bench.empty:
        bpv = (1 + bench).cumprod()
        bench_tbl = metric_table(bench, bpv, rf_annual)
    else:
        bench_tbl = {k: np.nan for k in strat}

    # tables
    comp = pd.DataFrame({"Strategy": strat, "S&P 500 (B&H)": bench_tbl})
    comp.to_csv(os.path.join(tdir, "performance_comparison.csv"))
    diag = ml_diagnostics(sector_map)
    if isinstance(diag["ic_by_sector"], pd.DataFrame) and not diag["ic_by_sector"].empty:
        diag["ic_by_sector"].to_csv(os.path.join(tdir, "ic_by_sector.csv"), index=False)
    cov = crisis_coverage(rebalance_dates)
    cov.to_csv(os.path.join(tdir, "crisis_coverage.csv"), index=False)

    # holdings by rebalance + period-by-period vs S&P 500 (Josh, 2026-07-02)
    holdings = holdings_table()
    if not holdings.empty:
        holdings.to_csv(os.path.join(tdir, "holdings_by_rebalance.csv"), index=False)
    period_cmp = period_comparison_table(results, bench)
    period_cmp.to_csv(os.path.join(tdir, "period_comparison.csv"), index=False)

    # figures
    plot_cumulative(results, bench)
    turn_path = os.path.join(C.BACKTEST_DIR, "turnover_log.csv")
    if os.path.exists(turn_path):
        plot_turnover(pd.read_csv(turn_path))
    reps = [rebalance_dates[0], rebalance_dates[len(rebalance_dates) // 2], rebalance_dates[-1]]
    for d in dict.fromkeys(reps):
        plot_frontier(pd.Timestamp(d).date().isoformat())

    outperf = strat["Annualized Return"] - (bench_tbl["Annualized Return"] or 0)
    lim = limitations or []

    md = f"""# ML-Driven Black-Litterman Portfolio — Backtest Report

## 1. Executive summary
Performance period **{C.BACKTEST_START} → {C.BACKTEST_END}**, quarterly rebalancing.
Strategy annualised return **{strat['Annualized Return']:.2%}** vs S&P 500
**{bench_tbl['Annualized Return'] if not np.isnan(bench_tbl['Annualized Return']) else float('nan'):.2%}**
(buy & hold) — {'out' if outperf > 0 else 'under'}performing by {abs(outperf):.2%} annualised.
Strategy Sharpe {strat['Sharpe Ratio']:.3f} vs benchmark {bench_tbl['Sharpe Ratio']:.3f}.

## 2. Cumulative return
![cumulative](figures/cumulative_return.png)

## 3. Efficient frontier (representative dates)
""" + "".join(
        f"![frontier]("
        f"figures/efficient_frontier_{pd.Timestamp(d).date().isoformat()}.png)\n"
        for d in dict.fromkeys(reps)
    ) + f"""

## 4. Performance metrics

| Metric | Strategy | S&P 500 (B&H) |
|---|---|---|
""" + "\n".join(
        f"| {k} | "
        + (f"{strat[k]:.2%}" if 'Ratio' not in k else f"{strat[k]:.3f}") + " | "
        + (f"{bench_tbl[k]:.2%}" if 'Ratio' not in k else f"{bench_tbl[k]:.3f}") + " |"
        for k in strat
    ) + f"""

## 5. Holdings by rebalance
Full holdings (ticker, sector, weight, r_hat, rank in sector) for every rebalance
date are written to `tables/holdings_by_rebalance.csv`. First and last rebalance
shown here as a sample:

**{pd.Timestamp(rebalance_dates[0]).date()}**

{_holdings_md(holdings, rebalance_dates[0]) if not holdings.empty else "_(no holdings recorded)_"}

**{pd.Timestamp(rebalance_dates[-1]).date()}**

{_holdings_md(holdings, rebalance_dates[-1]) if not holdings.empty else "_(no holdings recorded)_"}

## 6. Period-by-period: strategy vs S&P 500
Same holding window each row (not just the aggregate Section 4 comparison) — full
table also written to `tables/period_comparison.csv`.

{_period_cmp_md(period_cmp)}

## 7. ML quality diagnostics
- Mean Information Coefficient (rank corr, full universe): **{diag['mean_ic']:.4f}**
  (IC > 0.05 weakly predictive, > 0.1 good for cross-sectional equity — 08 §4.1)
- Mean directional accuracy: **{diag['mean_directional_accuracy']:.2%}** (50% = random)

IC and RMSE per sector are written to `tables/ic_by_sector.csv`.

## 8. Turnover & cost
![turnover](figures/turnover_over_time.png)

Total transaction cost paid over the backtest:
**{results['transaction_cost'].sum():.2%}** of portfolio value (cumulative drag).

## 9. Limitations (explicit — 08 §7)
- **Survivorship bias**: current S&P 500 list applied retroactively (01 §5, 09 §1).
- **Rolling-window crisis coverage**: see `tables/crisis_coverage.csv` — the 10-year
  window "forgets" crises (2008 GFC, 2020 COVID) as they age out.
- **SVR hyperparameter tuning** tuned once on a sample, not per stock (03 §4, 09 §4).
- **Sector classification** held fixed for the whole backtest (01 §3.4, 09 §3).
- **Market-cap reconstruction** approximates shares as constant (01 §3.3, 09 §2).
- **Overlapping 63-day targets** → effective sample size << row count (03 §2).
""" + ("".join(f"- {x}\n" for x in lim) if lim else "")

    path = os.path.join(C.REPORT_DIR, "final_report.md")
    with open(path, "w") as fh:
        fh.write(md)
    print(f"[M8] report written → {path}")
    return path
