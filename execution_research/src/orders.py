"""
orders.py — the parent orders every algorithm executes (experiment design A).

  1. draw BASE_N = ORDERS_PER_BUCKET (decision bar, ticker, side) triplets:
       decision bar t  uniform over out-of-sample bars with a full horizon after it
       ticker          uniform over that day's point-in-time Top-N (by trailing ADV)
       side            buy / sell with equal probability
  2. give every triplet each size in SIZE_BUCKETS_PCT_NAV
       → the size effect is measured on identical (time, stock, side) draws.
  3. reject a triplet (and redraw) if the window t … t+HORIZON contains an
     unadjusted corporate-action jump, a missing price or no ex-ante σ.

Sells assume the shares are already held (no portfolio / cash constraint here:
the object of study is execution, not the portfolio).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import constants as C
from .cost import floor_lot
from .data import Market


def generate(mk: Market, n_base: int = C.ORDERS_PER_BUCKET, buckets: list[float] = C.SIZE_BUCKETS_PCT_NAV,
             nav: float = C.NAV_THB, horizon: int = C.HORIZON_BARS, seed: int = C.SEED,
             period: str = "out") -> tuple[pd.DataFrame, dict]:
    """period: "out" = decisions after IN_SAMPLE_END (main experiment), "in" = up to it."""
    rng = np.random.default_rng(seed)
    idx = mk.close.index
    close, sigma, jump = mk.close.to_numpy(), mk.sigma.to_numpy(), mk.jump.to_numpy()
    col = {t: j for j, t in enumerate(mk.tickers)}
    split = int(np.searchsorted(idx, pd.Timestamp(C.IN_SAMPLE_END) + pd.Timedelta(days=1)))
    if period == "out":
        first, last = split, len(idx) - 1 - horizon      # need bars t+1 … t+horizon
    elif period == "in":
        first, last = 0, split - 1 - horizon             # window stays inside the in-sample period
    else:
        raise ValueError("period must be 'in' or 'out'")
    if last < first:
        raise ValueError(f"not enough {period}-sample bars for one horizon")
    day_of_bar = idx.normalize()

    rejected = {"jump": 0, "no_price": 0, "no_sigma": 0}
    base = []
    while len(base) < n_base:
        t = int(rng.integers(first, last + 1))
        members = mk.top.loc[day_of_bar[t]]
        names = list(members[members].index)
        if not names:
            continue
        tk = names[int(rng.integers(len(names)))]
        side = 1 if rng.random() < 0.5 else -1
        j = col[tk]
        win = slice(t, t + horizon + 1)
        if np.isnan(close[win, j]).any():
            rejected["no_price"] += 1
            continue
        if jump[t + 1: t + horizon + 1, j].any() or jump[t, j]:
            rejected["jump"] += 1
            continue
        if not sigma[t, j] > 0:
            rejected["no_sigma"] += 1
            continue
        base.append((t, tk, side))

    rows, oid = [], 1
    for b, (t, tk, side) in enumerate(base):
        j = col[tk]
        arrival = float(close[t, j])
        adv = float(mk.adv.loc[day_of_bar[t], tk])
        for pct in buckets:
            notional = pct * nav
            qty = floor_lot(notional / arrival)
            rows.append({"order_id": oid, "base_id": b, "ticker": tk, "side": side,
                         "bucket": f"{pct:.0%} NAV", "pct_nav": pct, "decision_i": t,
                         "decision_dt": idx[t], "hour": int(idx[t].hour), "arrival_price": arrival,
                         "qty": qty, "paper_notional": qty * arrival, "adv": adv,
                         "pct_adv": qty * arrival / adv, "sigma": float(sigma[t, j])})
            oid += 1
    orders = pd.DataFrame(rows)
    info = {"period": period, "n_base": n_base, "n_orders": len(orders), "rejected_draws": rejected,
            "first_decision_allowed": str(idx[first]), "last_decision_allowed": str(idx[last])}
    return orders, info
