"""
plots.py — the notebook's charts, one consistent style.

Each algorithm keeps the same color in every chart (fixed categorical order,
validated for color-vision deficiency). Two of the four hues sit below 3:1
contrast on the surface, so every multi-series chart is direct-labeled and
paired with a table in the notebook.
"""
from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from . import constants as C

ALGO_COLOR = {"MARKET": "#2a78d6", "TWAP": "#eb6834", "VWAP": "#1baf7a", "POV": "#eda100"}
SINGLE = "#2a78d6"
SURFACE, TEXT, TEXT_2, GRID = "#fcfcfb", "#1f1f1e", "#5f5e5a", "#e1e0d9"


def style():
    plt.rcParams.update({
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
        "axes.edgecolor": GRID, "axes.labelcolor": TEXT_2, "axes.titlecolor": TEXT,
        "axes.titlesize": 12, "axes.titleweight": "bold", "axes.titlelocation": "left",
        "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
        "grid.color": GRID, "grid.linewidth": 0.6, "axes.axisbelow": True,
        "xtick.color": TEXT_2, "ytick.color": TEXT_2, "font.size": 10,
        "legend.frameon": False, "lines.linewidth": 2.0, "lines.markersize": 7,
    })


def _spread_out(ys: dict[str, float], ax, min_frac: float = 0.05) -> dict[str, float]:
    """Nudge label y-positions apart so no two are closer than min_frac of the axis range."""
    lo, hi = ax.get_ylim()
    gap = (hi - lo) * min_frac
    names = sorted(ys, key=ys.get)
    pos = {}
    for k, n in enumerate(names):
        pos[n] = ys[n] if k == 0 else max(ys[n], pos[names[k - 1]] + gap)
    return pos


def _label_points(ax, points: dict[str, tuple[float, float]], text: dict[str, str], side: str = "right"):
    """Direct labels (text ink) beside each point, de-collided vertically."""
    pos = _spread_out({n: xy[1] for n, xy in points.items()}, ax)
    for n, (x, _) in points.items():
        label = "  " + text[n] if side == "right" else text[n] + "  "
        ax.text(x, pos[n], label, va="center", ha="left" if side == "right" else "right",
                color=TEXT, fontsize=9, clip_on=False)


def _label_ends(ax, x, series: dict[str, np.ndarray], fmt="{:.1f}"):
    """Direct label at the right end of each line (text ink, not series color)."""
    _label_points(ax, {n: (x[-1], y[-1]) for n, y in series.items()},
                  {n: f"{n}  {fmt.format(y[-1])}" for n, y in series.items()})


def _legend_below(ax):
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=4)


def volume_profile(profile: pd.Series):
    fig, ax = plt.subplots(figsize=(8, 3.4))
    labels = [f"{h:02d}:00" for h in profile.index]
    bars = ax.bar(labels, profile.values * 100, color=SINGLE, width=0.6)
    ax.bar_label(bars, fmt="%.1f%%", color=TEXT, fontsize=9, padding=2)
    ax.set_ylabel("share of daily traded value (%)")
    ax.set_title("Intraday volume profile (in-sample 2023–24) — input to VWAP")
    ax.grid(axis="x", visible=False)
    fig.tight_layout()
    return fig


def universe_frequency(top: pd.DataFrame, start: str):
    freq = top.loc[start:].mean().sort_values()
    freq = freq[freq > 0]
    fig, ax = plt.subplots(figsize=(8, 0.3 * len(freq) + 0.8))
    bars = ax.barh(freq.index, freq.values * 100, color=SINGLE, height=0.6)
    ax.bar_label(bars, fmt="%.0f%%", color=TEXT, fontsize=8, padding=2)
    ax.set_xlabel("share of out-of-sample days in the point-in-time Top 10 (%)")
    ax.set_title("Who is in the Top 10 by trailing 20-day traded value")
    ax.grid(axis="y", visible=False)
    fig.tight_layout()
    return fig


def example_schedule(fills: pd.DataFrame, order: pd.Series):
    """Cumulative % filled per algo for one parent order."""
    fig, ax = plt.subplots(figsize=(8, 3.8))
    ends = {}
    x_all = np.arange(0, C.HORIZON_BARS + 1)
    for a in C.ALGOS:
        f = fills[(fills.order_id == order.order_id) & (fills.algo == a)]
        cum = np.zeros(len(x_all))
        for _, r in f.iterrows():
            cum[int(r.slice_k):] += r.qty
        y = cum / order.qty * 100
        ax.step(x_all, y, where="post", color=ALGO_COLOR[a], label=a)
        ends[a] = y
    _label_points(ax, {a: (1, y[1]) for a, y in ends.items()},
                  {a: f"{a} {y[1]:.0f}%" for a, y in ends.items()}, side="left")
    ax.set_xlim(0, C.HORIZON_BARS + 0.3)
    ax.set_xticks(x_all, ["t"] + [f"t+{k}" for k in x_all[1:]])
    ax.set_ylabel("cumulative filled (%)")
    ax.set_title(f"How each algo works one order — {order.ticker} {order.bucket} ({order.pct_adv:.2%} of ADV)\n"
                 f"decided at the {pd.Timestamp(order.decision_dt):%Y-%m-%d %H:%M} close; labels = filled in bar t+1")
    _legend_below(ax)
    fig.tight_layout()
    return fig


def is_by_size(summ: pd.DataFrame, col: str = "is_mean", title: str = "Mean implementation shortfall by order size",
               ylabel: str = "bps", ci: bool = True):
    fig, ax = plt.subplots(figsize=(8.5, 4.2))
    ends = {}
    for a in C.ALGOS:
        g = summ[summ.algo == a].sort_values("pct_nav")
        x = g["pct_nav"].to_numpy() * 100
        y = g[col].to_numpy()
        if ci and "is_ci_lo" in g:
            ax.fill_between(x, g["is_ci_lo"], g["is_ci_hi"], color=ALGO_COLOR[a], alpha=0.12, linewidth=0)
        ax.plot(x, y, marker="o", color=ALGO_COLOR[a], label=a)
        ends[a] = y
    _label_ends(ax, x, ends)
    ax.set_xticks(x, [f"{v:g}%" for v in x])
    ax.set_xlim(x[0] - 1, x[-1] + 4)
    ax.set_xlabel("order size (% of NAV 100M)")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    _legend_below(ax)
    fig.tight_layout()
    return fig


def frontier(summ: pd.DataFrame):
    fig, ax = plt.subplots(figsize=(8.5, 4.6))
    ends = {}
    for a in C.ALGOS:
        g = summ[summ.algo == a].sort_values("pct_nav")
        ax.plot(g["is_std"], g["is_mean"], marker="o", color=ALGO_COLOR[a], label=a)
        ends[a] = (g["is_std"].iloc[-1], g["is_mean"].iloc[-1])
    lo, hi = ax.get_xlim()
    ax.set_xlim(lo, hi + (hi - lo) * 0.08)
    # put each label to the right of the rightmost line in its cluster so it never crosses a line
    right = {a: max(x for b, (x, y) in ends.items() if abs(x - ends[a][0]) < 10) + 0.8 for a in ends}
    _label_points(ax, {a: (right[a], y) for a, (x, y) in ends.items()}, {a: a for a in ends})
    ax.set_xlabel("risk: std of IS per order (bps)")
    ax.set_ylabel("cost: mean IS (bps)")
    ax.set_title("Cost–risk frontier — each line runs 1% → 5% → 10% → 25% NAV upward")
    _legend_below(ax)
    fig.tight_layout()
    return fig


def by_group(table: pd.DataFrame, group: str, bucket: str, title: str, xlabel: str):
    t = table[table.bucket == bucket].set_index(group)
    fig, ax = plt.subplots(figsize=(8.5, 4.0))
    x = np.arange(len(t))
    ends = {}
    for a in C.ALGOS:
        ax.plot(x, t[a].to_numpy(), marker="o", color=ALGO_COLOR[a], label=a)
        ends[a] = t[a].to_numpy()
    _label_ends(ax, x, ends)
    ax.set_xticks(x, [f"{v:02d}:00" if isinstance(v, (int, np.integer)) else str(v) for v in t.index])
    ax.set_xlim(-0.3, len(t) - 1 + 0.9)
    ax.set_xlabel(xlabel)
    ax.set_ylabel("mean IS (bps)")
    ax.set_title(title)
    _legend_below(ax)
    fig.tight_layout()
    return fig


def sensitivity(sens: pd.DataFrame, bucket: str):
    params = list(dict.fromkeys(sens["param"]))
    fig, axes = plt.subplots(1, len(params), figsize=(3.4 * len(params), 3.6), sharey=True)
    for ax, prm in zip(np.atleast_1d(axes), params):
        g = sens[(sens.param == prm) & (sens.bucket == bucket)]
        for a in C.ALGOS:
            h = g[g.algo == a].sort_values("value")
            ax.plot(h["value"], h["is_bps"], marker="o", color=ALGO_COLOR[a], label=a)
        base = g[g.is_base]["value"].iloc[0]
        ax.axvline(base, color=TEXT_2, lw=0.8, ls=":")
        ax.set_title(prm, fontsize=10)
        ax.set_xticks(sorted(g["value"].unique()))
    np.atleast_1d(axes)[0].set_ylabel(f"mean IS (bps), {bucket}")
    np.atleast_1d(axes)[0].legend(loc="upper left", fontsize=8)
    fig.suptitle(f"Sensitivity, one parameter at a time ({bucket}; dotted = base value)",
                 x=0.01, ha="left", fontweight="bold", color=TEXT)
    fig.tight_layout()
    return fig
