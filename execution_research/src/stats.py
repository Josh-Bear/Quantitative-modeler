"""
stats.py — summaries, paired significance tests, breakdowns and sensitivity.

Every algo executes the same parent orders, so algo differences are tested
PAIRED on order_id: d_i = IS_a,i − IS_b,i. Reported per size bucket:
  mean d, bootstrap 95 % CI of the mean, paired t-test p, Wilcoxon signed-rank p,
  Holm-adjusted p (over all algo pairs within the bucket).
"""
from __future__ import annotations

from itertools import combinations

import numpy as np
import pandas as pd
from scipy import stats as sps

from . import constants as C
from .engine import COMPONENTS, Arrays, Params, run


def bucket_order(df: pd.DataFrame) -> list[str]:
    return list(df.sort_values("pct_nav")["bucket"].drop_duplicates())


def _boot_ci(x: np.ndarray, n: int = C.BOOTSTRAP_N, seed: int = C.SEED, alpha: float = C.ALPHA):
    x = x[np.isfinite(x)]
    if len(x) < 2:
        return np.nan, np.nan
    rng = np.random.default_rng(seed)
    means = x[rng.integers(0, len(x), (n, len(x)))].mean(axis=1)
    return float(np.quantile(means, alpha / 2)), float(np.quantile(means, 1 - alpha / 2))


def summary(res: pd.DataFrame) -> pd.DataFrame:
    """One row per bucket × algo."""
    rows = []
    for (b, a), g in res.groupby(["bucket", "algo"], sort=False):
        x = g["is_bps"].to_numpy()
        lo, hi = _boot_ci(x)
        rows.append({"bucket": b, "pct_nav": g["pct_nav"].iloc[0], "algo": a, "n": len(g),
                     "pct_adv_mean": g["pct_adv"].mean(),
                     "is_mean": x.mean(), "is_ci_lo": lo, "is_ci_hi": hi,
                     "is_median": np.median(x), "is_std": x.std(ddof=1),
                     **{f"{k}_mean": g[f"{k}_bps"].mean() for k in COMPONENTS},
                     "vs_ivwap_mean": g["vs_ivwap_bps"].mean(),
                     "fill_rate_mean": g["fill_rate"].mean(),
                     "fully_filled_share": (g["fill_rate"] >= 1.0).mean(),
                     "bars_used_mean": g["bars_used"].mean(),
                     "max_participation_p95": g["max_participation"].quantile(0.95)})
    out = pd.DataFrame(rows)
    out["algo"] = pd.Categorical(out["algo"], C.ALGOS, ordered=True)
    return out.sort_values(["pct_nav", "algo"]).reset_index(drop=True)


def holm(p: np.ndarray) -> np.ndarray:
    p = np.asarray(p, float)
    order = np.argsort(p)
    m = len(p)
    adj = np.empty(m)
    running = 0.0
    for rank, k in enumerate(order):
        running = max(running, (m - rank) * p[k])
        adj[k] = min(running, 1.0)
    return adj


def paired_tests(res: pd.DataFrame, metric: str = "is_bps") -> pd.DataFrame:
    """All algo pairs within each bucket. d = a − b (negative → a is cheaper)."""
    rows = []
    for b in bucket_order(res):
        wide = res[res["bucket"] == b].pivot(index="order_id", columns="algo", values=metric)
        block = []
        for a1, a2 in combinations([a for a in C.ALGOS if a in wide.columns], 2):
            d = (wide[a1] - wide[a2]).dropna().to_numpy()
            lo, hi = _boot_ci(d)
            t_p = sps.ttest_rel(wide[a1], wide[a2], nan_policy="omit").pvalue
            w_p = sps.wilcoxon(d).pvalue if np.any(d != 0) else 1.0
            block.append({"bucket": b, "a": a1, "b": a2, "n": len(d), "mean_diff": d.mean(),
                          "ci_lo": lo, "ci_hi": hi, "share_a_cheaper": (d < 0).mean(),
                          "t_p": t_p, "wilcoxon_p": w_p})
        if block:
            adj = holm([r["t_p"] for r in block])
            for r, ap in zip(block, adj):
                r["t_p_holm"] = ap
                r["significant"] = ap < C.ALPHA
        rows.extend(block)
    return pd.DataFrame(rows)


def breakdown(res: pd.DataFrame, by: str, metric: str = "is_bps") -> pd.DataFrame:
    """Mean metric by bucket × group × algo (group columns: hour, year, vol_tercile, ...)."""
    t = res.groupby(["pct_nav", "bucket", by, "algo"], observed=True)[metric].mean().unstack("algo")
    return t[[a for a in C.ALGOS if a in t.columns]].reset_index().drop(columns="pct_nav")


def add_groups(res: pd.DataFrame) -> pd.DataFrame:
    """Volatility tercile of the ex-ante σ, computed on the base draws (same for every size)."""
    base = res.drop_duplicates("base_id")[["base_id", "sigma"]]
    base["vol_tercile"] = pd.qcut(base["sigma"], 3, labels=["low σ", "mid σ", "high σ"])
    return res.merge(base[["base_id", "vol_tercile"]], on="base_id")


def best_algo(summ: pd.DataFrame) -> pd.DataFrame:
    i = summ.groupby("bucket", observed=True)["is_mean"].idxmin()
    return summ.loc[i, ["bucket", "pct_adv_mean", "algo", "is_mean", "is_std"]].sort_values("pct_adv_mean")


def sensitivity(orders: pd.DataFrame, ar: Arrays, base: Params = Params(),
                grid: dict = C.SENSITIVITY) -> pd.DataFrame:
    """One-at-a-time: change one parameter, keep the rest at base. Mean IS per bucket × algo."""
    key = {"SPREAD_TICKS": "spread_ticks", "IMPACT_Y": "impact_y",
           "SCHEDULE_CAP": "schedule_cap", "HORIZON_BARS": "horizon"}
    rows = []
    for name, values in grid.items():
        for v in values:
            p = base.with_(**{key[name]: v})
            res, _ = run(orders, ar, p)
            m = res.groupby(["pct_nav", "bucket", "algo"])["is_bps"].mean().reset_index()
            m["param"], m["value"] = name, v
            m["is_base"] = getattr(base, key[name]) == v
            rows.append(m)
    out = pd.concat(rows, ignore_index=True)
    rank = out.groupby(["param", "value", "bucket"])["is_bps"].rank(method="min")
    out["rank"] = rank.astype(int)
    return out
