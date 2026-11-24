"""
plots.py — the notebook's charts, one consistent style.

Six algorithms, but no six-hue palette stays distinguishable on every pair
(validated with the dataviz palette checker), so the encoding is composite:
four hues that pass all-pairs (MARKET blue, TWAP yellow, VWAP green, POV family
pink) and the three POV variants share the pink hue, separated by line style +
marker (POV10 solid ●, POV5 dashed ■, POV5/10 dotted ▲). Every multi-series
chart also has a legend, de-collided direct labels and a table in the notebook.
"""
from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from . import constants as C

_BLUE, _YELLOW, _GREEN, _PINK = "#2a78d6", "#eda100", "#008300", "#e87ba4"
ALGO_STYLE = {                       # algo → (color, linestyle, marker)
    "MARKET": (_BLUE, "-", "o"),
    "TWAP": (_YELLOW, "-", "o"),
    "VWAP": (_GREEN, "-", "o"),
    "POV10": (_PINK, "-", "o"),
    "POV5": (_PINK, "--", "s"),
    "POV5/10": (_PINK, ":", "^"),
}
RAMP = ["#86b6ef", "#2a78d6", "#104281"]          # one-hue ordinal ramp (light → dark)
SINGLE = _BLUE
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


def _kw(algo: str) -> dict:
    c, ls, m = ALGO_STYLE[algo]
    return {"color": c, "linestyle": ls, "marker": m, "label": algo}


def _spread_out(ys: dict[str, float], ax, min_frac: float = 0.045) -> dict[str, float]:
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
    _label_points(ax, {n: (x[-1], y[-1]) for n, y in series.items()},
                  {n: f"{n}  {fmt.format(y[-1])}" for n, y in series.items()})


def _legend_below(ax, ncol: int = 6):
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=ncol)


def _bucket_cols(df: pd.DataFrame) -> list[str]:
    return sorted(df.columns, key=lambda b: float(str(b).split("%")[0]))


# ─── data ─────────────────────────────────────────────────────────────────────
def volume_profile(profile: pd.DataFrame):
    """Median rolling profile per bar hour, whiskers = 5th–95th percentile across days."""
    p = profile.dropna() * 100
    med, lo, hi = p.median(), p.quantile(0.05), p.quantile(0.95)
    fig, ax = plt.subplots(figsize=(8, 3.6))
    labels = [f"{h:02d}:00" for h in p.columns]
    bars = ax.bar(labels, med.values, color=SINGLE, width=0.6,
                  yerr=[med - lo, hi - med], ecolor=TEXT_2, capsize=4, error_kw={"lw": 1})
    for b, v, top in zip(bars, med.values, hi.values):
        ax.text(b.get_x() + b.get_width() / 2, top + 0.6, f"{v:.1f}%", ha="center", color=TEXT, fontsize=9)
    ax.set_ylabel("share of daily traded value (%)")
    ax.set_title(f"VWAP input: rolling {C.PROFILE_DAYS}-day volume profile (median, whiskers 5–95 %)")
    ax.grid(axis="x", visible=False)
    fig.tight_layout()
    return fig


def profile_over_time(profile: pd.DataFrame, hours=(10, 17, 11)):
    p = profile.dropna() * 100
    fig, ax = plt.subplots(figsize=(9, 3.8))
    ends = {}
    for h, col in zip(hours, RAMP):
        ax.plot(p.index, p[h], color=col, lw=1.6, label=f"{h:02d}:00")
        ends[f"{h:02d}:00"] = (p.index[-1], p[h].iloc[-1])
    _label_points(ax, ends, {k: k for k in ends})
    ax.set_ylabel("share of daily value (%)")
    ax.set_title("How the profile drifts — the VWAP weights move with the market")
    _legend_below(ax, 3)
    fig.tight_layout()
    return fig


# ─── algorithms ───────────────────────────────────────────────────────────────
def example_schedule(fills: pd.DataFrame, order: pd.Series):
    """Cumulative % filled per algo for one parent order."""
    fig, ax = plt.subplots(figsize=(9, 4.2))
    ends = {}
    x_all = np.arange(0, C.HORIZON_BARS + 1)
    for a in C.ALGOS:
        f = fills[(fills.order_id == order.order_id) & (fills.algo == a)]
        cum = np.zeros(len(x_all))
        for _, r in f.iterrows():
            cum[int(r.slice_k):] += r.qty
        y = cum / order.qty * 100
        kw = _kw(a)
        kw.pop("marker")
        ax.step(x_all, y, where="post", **kw)
        ends[a] = y
    _label_points(ax, {a: (1, y[1]) for a, y in ends.items()},
                  {a: f"{a} {y[1]:.0f}%" for a, y in ends.items()}, side="left")
    ax.set_xlim(-0.9, C.HORIZON_BARS + 0.3)
    ax.set_xticks(x_all, ["t"] + [f"t+{k}" for k in x_all[1:]])
    ax.set_ylabel("cumulative filled (%)")
    ax.set_title(f"How each algo works one order — {order.ticker} {order.bucket} ({order.pct_adv:.2%} of ADV)\n"
                 f"decided at the {pd.Timestamp(order.decision_dt):%Y-%m-%d %H:%M} close; labels = filled in bar t+1")
    _legend_below(ax)
    fig.tight_layout()
    return fig


# ─── results ──────────────────────────────────────────────────────────────────
def is_by_size(summ: pd.DataFrame, col: str = "is_mean", title: str = "Mean implementation shortfall by order size",
               ylabel: str = "bps", ci: bool = True, algos=None):
    algos = algos or C.ALGOS
    fig, ax = plt.subplots(figsize=(9, 4.6))
    ends = {}
    for a in algos:
        g = summ[summ.algo == a].sort_values("pct_nav")
        x = g["pct_nav"].to_numpy() * 100
        y = g[col].to_numpy()
        if ci and "is_ci_lo" in g:
            ax.fill_between(x, g["is_ci_lo"], g["is_ci_hi"], color=ALGO_STYLE[a][0], alpha=0.08, linewidth=0)
        ax.plot(x, y, **_kw(a))
        ends[a] = y
    _label_ends(ax, x, ends)
    ax.set_xticks(x, [f"{v:g}%" for v in x])
    ax.set_xlim(x[0] - 1, x[-1] + 5)
    ax.set_xlabel("order size (% of NAV 100M)")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    _legend_below(ax)
    fig.tight_layout()
    return fig


# bar fills: same hue rule as the lines; the three POV variants are separated by hatch
ALGO_HATCH = {"POV10": "", "POV5": "///", "POV5/10": "..."}


def size_algo_bars(summ: pd.DataFrame):
    """Grouped bars, one group per order size: mean IS (±95 % CI) on top, IS std below.
    The cheapest / least-risky algo in each group is value-labelled."""
    sizes = sorted(summ["pct_nav"].unique())
    algos = [a for a in C.ALGOS if a in set(summ["algo"])]
    n = len(algos)
    width = 0.8 / n
    x = np.arange(len(sizes))
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 7.4), sharex=True,
                                   gridspec_kw={"height_ratios": [3, 2], "hspace": 0.12})
    for k, a in enumerate(algos):
        g = summ[summ.algo == a].set_index("pct_nav").reindex(sizes)
        pos = x - 0.4 + width * (k + 0.5)
        color = ALGO_STYLE[a][0]
        hatch = ALGO_HATCH.get(a, "")
        yerr = [g["is_mean"] - g["is_ci_lo"], g["is_ci_hi"] - g["is_mean"]]
        kw = dict(width=width, color=color, edgecolor=SURFACE, linewidth=1.5, hatch=hatch, label=a)
        ax1.bar(pos, g["is_mean"], yerr=yerr, ecolor=TEXT_2, capsize=2, error_kw={"lw": 0.8}, **kw)
        ax2.bar(pos, g["is_std"], **kw)
    # value-label only the best bar per group (lowest mean cost / lowest risk)
    for ax, col, fmt in ((ax1, "is_mean", "{:.1f}"), (ax2, "is_std", "{:.0f}")):
        for i, sz in enumerate(sizes):
            g = summ[summ.pct_nav == sz].set_index("algo").reindex(algos)
            k = int(np.nanargmin(g[col].to_numpy()))
            top = g[col].iloc[k] + (g["is_ci_hi"].iloc[k] - g["is_mean"].iloc[k] if col == "is_mean" else 0)
            ax.text(x[i] - 0.4 + width * (k + 0.5), top + 0.8, fmt.format(g[col].iloc[k]),
                    ha="center", va="bottom", color=TEXT, fontsize=8)
        ax.grid(axis="x", visible=False)
    ax1.set_ylabel("cost: mean IS (bps), ±95 % CI")
    ax2.set_ylabel("risk: std of IS (bps)")
    ax1.set_title("Cost and risk by order size and algorithm (labels = best in each group)")
    ax2.set_xticks(x, [f"{s:.0%} NAV" for s in sizes])
    ax2.set_xlabel(f"order size (% of NAV {C.NAV_THB / 1e6:,.0f}M)")
    handles, labels = ax1.get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=n, frameon=False)
    fig.subplots_adjust(left=0.08, right=0.98, top=0.94, bottom=0.13)
    return fig


def frontier(summ: pd.DataFrame):
    fig, ax = plt.subplots(figsize=(9, 4.8))
    ends = {}
    for a in C.ALGOS:
        g = summ[summ.algo == a].sort_values("pct_nav")
        ax.plot(g["is_std"], g["is_mean"], **_kw(a))
        ends[a] = (g["is_std"].iloc[-1], g["is_mean"].iloc[-1])
    lo, hi = ax.get_xlim()
    ax.set_xlim(lo, hi + (hi - lo) * 0.12)
    # label to the right of the rightmost line in its cluster so it never crosses a line
    right = {a: max(x for (x, _) in ends.values() if abs(x - ends[a][0]) < 8) + 0.8 for a in ends}
    _label_points(ax, {a: (right[a], y) for a, (x, y) in ends.items()}, {a: a for a in ends})
    ax.set_xlabel("risk: std of IS per order (bps)")
    ax.set_ylabel("cost: mean IS (bps)")
    ax.set_title("Cost–risk frontier — each line runs 1% → 5% → 10% → 25% NAV upward")
    _legend_below(ax)
    fig.tight_layout()
    return fig


def by_group(table: pd.DataFrame, group: str, bucket: str, title: str, xlabel: str):
    t = table[table.bucket == bucket].set_index(group)
    fig, ax = plt.subplots(figsize=(9, 4.4))
    x = np.arange(len(t))
    ends = {}
    for a in C.ALGOS:
        ax.plot(x, t[a].to_numpy(), **_kw(a))
        ends[a] = t[a].to_numpy()
    _label_ends(ax, x, ends)
    ticks = [f"{v:02d}:00" if group == "hour" else str(v) for v in t.index]
    ax.set_xticks(x, ticks)
    ax.set_xlim(-0.3, len(t) - 1 + 1.1)
    ax.set_xlabel(xlabel)
    ax.set_ylabel("mean IS (bps)")
    ax.set_title(title)
    _legend_below(ax)
    fig.tight_layout()
    return fig


def sensitivity(sens: pd.DataFrame, bucket: str):
    params = list(dict.fromkeys(sens["param"]))
    fig, axes = plt.subplots(1, len(params), figsize=(3.8 * len(params), 3.9), sharey=True)
    axes = np.atleast_1d(axes)
    for ax, prm in zip(axes, params):
        g = sens[(sens.param == prm) & (sens.bucket == bucket)]
        for a in C.ALGOS:
            h = g[g.algo == a].sort_values("value")
            ax.plot(h["value"], h["is_bps"], **_kw(a))
        ax.axvline(g[g.is_base]["value"].iloc[0], color=TEXT_2, lw=0.8, ls=":")
        ax.set_title(prm, fontsize=10)
        ax.set_xticks(sorted(g["value"].unique()))
    axes[0].set_ylabel(f"mean IS (bps), {bucket}")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=6, frameon=False)
    fig.suptitle(f"Sensitivity, one parameter at a time ({bucket}; dotted = base value)",
                 x=0.01, ha="left", fontweight="bold", color=TEXT)
    fig.tight_layout(rect=(0, 0.08, 1, 1))
    return fig
