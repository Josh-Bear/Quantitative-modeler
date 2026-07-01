"""
PDF summary builder — renders the backtest results in output/ into a single
self-contained PDF (output/report/final_report.pdf).

Uses matplotlib's PdfPages backend, so it needs NO external system dependency
(no LaTeX, no headless Chromium). Metrics reuse src/evaluation.py — nothing is
recomputed from the raw backtest. Run after a backtest exists:

    python make_pdf.py                       # from the project root
    # or it is called automatically at the end of run.py
"""
from __future__ import annotations

import os
from typing import Optional

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

from . import constants as C
from . import evaluation as ev
from . import data_pipeline as dp
from . import backtest as bt

_PAGE = (8.27, 11.69)   # A4 portrait, inches


def _periods(results: pd.DataFrame) -> list[tuple]:
    if "period_end" in results.columns:
        return list(zip(results["date"], results["period_end"]))
    bounds = list(results["date"]) + [pd.Timestamp(C.BACKTEST_END)]
    return list(zip(bounds[:-1], bounds[1:]))


def _fmt(name: str, v) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "n/a"
    return f"{v:.3f}" if "Ratio" in name else f"{v:.2%}"


def build_pdf_report(path: Optional[str] = None) -> Optional[str]:
    """Compose output/report/final_report.pdf from the saved backtest artifacts."""
    C.ensure_dirs()
    rr = os.path.join(C.BACKTEST_DIR, "realized_returns.parquet")
    if not os.path.exists(rr):
        print("[PDF] no realized_returns.parquet — run a backtest first.")
        return None
    path = path or os.path.join(C.REPORT_DIR, "final_report.pdf")

    results = pd.read_parquet(rr)
    results["date"] = pd.to_datetime(results["date"])
    if "period_end" in results.columns:
        results["period_end"] = pd.to_datetime(results["period_end"])

    rf = bt.get_risk_free_rate()
    r = results.set_index("date")["period_return"]
    pv = results.set_index("date")["portfolio_value"]
    strat = ev.metric_table(r, pv, rf)

    bench = ev.benchmark_series(_periods(results))
    bench_tbl = (ev.metric_table(bench, (1 + bench).cumprod(), rf)
                 if not bench.empty else {k: np.nan for k in strat})

    try:
        sector_map = dp.load_sector_map()
        diag = ev.ml_diagnostics(sector_map)
    except Exception:  # noqa: BLE001
        diag = {"mean_ic": np.nan, "mean_directional_accuracy": np.nan}

    with PdfPages(path) as pdf:
        _page_summary(pdf, results, strat, bench_tbl, rf)
        _page_cumulative(pdf, results, bench)
        _page_frontiers(pdf)
        _page_turnover_and_diag(pdf, results, diag)
    print(f"[PDF] report written -> {path}")
    return path


# ─────────────────────────────────────────────────────────────────────────────
# Page 1 — title, executive summary, metrics table
# ─────────────────────────────────────────────────────────────────────────────
def _page_summary(pdf, results, strat, bench_tbl, rf):
    fig = plt.figure(figsize=_PAGE)
    fig.text(0.5, 0.95, "ML-Driven Black-Litterman Portfolio",
             ha="center", fontsize=18, fontweight="bold")
    fig.text(0.5, 0.915, "Backtest Summary Report", ha="center", fontsize=13, color="#444")

    outperf = strat["Annualized Return"] - (bench_tbl["Annualized Return"]
                                            if not np.isnan(bench_tbl["Annualized Return"]) else 0)
    summary = (
        f"Performance period: {C.BACKTEST_START} → {C.BACKTEST_END}   "
        f"(quarterly rebalancing, {len(results)} periods)\n"
        f"Risk-free rate (FRED DTB3): {rf:.2%} annual\n\n"
        f"Strategy annualised return: {strat['Annualized Return']:.2%}   "
        f"vs S&P 500 (buy & hold): "
        f"{bench_tbl['Annualized Return']:.2%}\n"
        f"→ {'OUT' if outperf > 0 else 'UNDER'}performing by "
        f"{abs(outperf):.2%} annualised.\n"
        f"Strategy Sharpe: {strat['Sharpe Ratio']:.3f}   "
        f"vs benchmark: {bench_tbl['Sharpe Ratio']:.3f}"
    )
    fig.text(0.08, 0.83, summary, ha="left", va="top", fontsize=10.5, family="monospace")

    # metrics table
    rows = list(strat.keys())
    cell = [[_fmt(k, strat[k]), _fmt(k, bench_tbl[k])] for k in rows]
    ax = fig.add_axes([0.08, 0.40, 0.84, 0.30]); ax.axis("off")
    tbl = ax.table(cellText=cell, rowLabels=rows,
                   colLabels=["Strategy", "S&P 500 (B&H)"],
                   cellLoc="center", rowLoc="left", loc="center")
    tbl.auto_set_font_size(False); tbl.set_fontsize(10); tbl.scale(1, 1.6)
    for (rr, cc), c in tbl.get_celld().items():
        if rr == 0 or cc == -1:
            c.set_text_props(fontweight="bold")
        c.set_edgecolor("#cccccc")
    fig.text(0.08, 0.36, "Performance & risk metrics (periods_per_year = 4)",
             fontsize=9, style="italic", color="#666")

    notes = (
        "Notes / limitations (see 08_EVALUATION_METRICS.md §7):\n"
        "  • Survivorship bias: current S&P 500 list applied retroactively.\n"
        "  • Rolling 10-year window forgets old crises (2008 GFC, 2020 COVID) as they age out.\n"
        "  • Market cap reconstruction approximates shares as constant.\n"
        "  • SVR tuned once on a sample; sector classification held fixed; overlapping 63-day\n"
        "    targets shrink the effective sample size.\n"
        "  • Research scaffold — illustrative, not a profitable strategy."
    )
    fig.text(0.08, 0.30, notes, ha="left", va="top", fontsize=9, color="#333")
    fig.text(0.5, 0.03, "Generated by bl_model_port_optimization", ha="center",
             fontsize=8, color="#999")
    pdf.savefig(fig); plt.close(fig)


# ─────────────────────────────────────────────────────────────────────────────
# Page 2 — cumulative return
# ─────────────────────────────────────────────────────────────────────────────
def _page_cumulative(pdf, results, bench):
    fig, ax = plt.subplots(figsize=_PAGE)
    ax.plot(results["date"], results["portfolio_value"], marker="o", lw=2, label="BL strategy")
    if not bench.empty:
        bpv = (1 + bench).cumprod()
        ax.plot(bpv.index, bpv.values, marker="s", lw=2, ls="--", label="S&P 500 (buy & hold)")
    ax.set_title("Cumulative return: BL strategy vs S&P 500", fontsize=14)
    ax.set_ylabel("Normalised value (start = 1.0)"); ax.set_xlabel("Rebalance date")
    ax.legend(); ax.grid(alpha=0.3)
    fig.autofmt_xdate()
    pdf.savefig(fig); plt.close(fig)


# ─────────────────────────────────────────────────────────────────────────────
# Page 3 — efficient frontiers at representative dates
# ─────────────────────────────────────────────────────────────────────────────
def _page_frontiers(pdf):
    files = sorted(f[:-len("_frontier.parquet")] for f in os.listdir(C.PORTFOLIO_DIR)
                   if f.endswith("_frontier.parquet")) if os.path.isdir(C.PORTFOLIO_DIR) else []
    if not files:
        return
    pick = sorted(set([files[0], files[len(files) // 2], files[-1]]))
    fig, axes = plt.subplots(len(pick), 1, figsize=_PAGE, squeeze=False)
    for ax, d in zip(axes[:, 0], pick):
        fr = pd.read_parquet(os.path.join(C.PORTFOLIO_DIR, f"{d}_frontier.parquet"))
        ax.plot(fr["volatility"], fr["target_return"], "-o", ms=3, label="Efficient frontier")
        pnpz = os.path.join(C.PORTFOLIO_DIR, f"{d}.npz")
        bnpz = os.path.join(C.BL_DIR, f"{d}.npz")
        if os.path.exists(pnpz) and os.path.exists(bnpz):
            z = np.load(pnpz, allow_pickle=True); b = np.load(bnpz); w = z["w_star"]
            ax.plot(np.sqrt(w @ b["Sigma"] @ w), w @ b["mu_BL"], "r*", ms=16, label="Max Sharpe")
        ax.set_title(f"Efficient frontier @ {d}", fontsize=11)
        ax.set_xlabel("Volatility (63-day)"); ax.set_ylabel("Expected return (63-day)")
        ax.legend(fontsize=8); ax.grid(alpha=0.3)
    fig.suptitle("Efficient frontier at representative rebalance dates", fontsize=14)
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    pdf.savefig(fig); plt.close(fig)


# ─────────────────────────────────────────────────────────────────────────────
# Page 4 — turnover + ML diagnostics
# ─────────────────────────────────────────────────────────────────────────────
def _page_turnover_and_diag(pdf, results, diag):
    turn_path = os.path.join(C.BACKTEST_DIR, "turnover_log.csv")
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=_PAGE,
                                   gridspec_kw={"height_ratios": [2, 1]})
    if os.path.exists(turn_path):
        turn = pd.read_csv(turn_path)
        changed = (1 - turn["overlap_pct"].fillna(0)) * 100
        ax1.bar(range(len(turn)), changed, color="steelblue")
        ax1.set_xticks(range(len(turn)))
        ax1.set_xticklabels(turn["date"].astype(str).str[:10], rotation=45, ha="right", fontsize=7)
        ax1.set_ylabel("% of universe changed")
    ax1.set_title("Universe turnover per rebalance", fontsize=13); ax1.grid(alpha=0.3, axis="y")

    ax2.axis("off")
    text = (
        "ML quality diagnostics (full universe, before selection):\n"
        f"   Mean Information Coefficient : {diag.get('mean_ic', float('nan')):.4f}"
        "   (>0.05 weakly predictive, >0.1 good)\n"
        f"   Mean directional accuracy    : {diag.get('mean_directional_accuracy', float('nan')):.2%}"
        "   (50% = random)\n\n"
        f"Total transaction cost over backtest : {results['transaction_cost'].sum():.2%} "
        "of portfolio value (cumulative drag)."
    )
    ax2.text(0.0, 0.9, text, va="top", ha="left", fontsize=10, family="monospace")
    fig.tight_layout()
    pdf.savefig(fig); plt.close(fig)
