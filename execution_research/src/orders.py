"""
orders.py — the parent orders every algorithm executes (experiment design A).

  1. draw N_BASE = ORDERS_PER_BUCKET (decision bar, ticker, side) triplets:
       decision bar t  uniform over every OBSERVED bar (not an inserted empty 14:00)
                       from the first day on which ADV, the rolling VWAP profile and
                       σ all exist, up to the last bar with a full horizon after it
                       (≈ Feb 2023 → Nov 2026)
       ticker          uniform over the 10 locked TICKERS
       side            buy / sell with equal probability
  2. give every triplet each size in SIZE_BUCKETS_PCT_NAV
       → the size effect is measured on identical (time, stock, side) draws.
  3. reject a triplet (and redraw) if its window has an unadjusted corporate-action
     jump, a missing price or no ex-ante σ.

Sells assume the shares are already held (no portfolio / cash constraint here:
the object of study is execution, not the portfolio).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import constants as C
from .cost import floor_lot
from .data import Market


def first_decision_bar(mk: Market) -> int:
    """First bar of the first day with ADV for every ticker and a VWAP profile."""
    ok = mk.adv.notna().all(axis=1) & mk.profile.notna().all(axis=1).reindex(mk.adv.index, fill_value=False)
    if not ok.any():
        raise ValueError("no day with both ADV and a VWAP profile")
    return int(np.searchsorted(mk.close.index, ok.idxmax()))


def generate(mk: Market, n_base: int = C.ORDERS_PER_BUCKET, buckets: list[float] = C.SIZE_BUCKETS_PCT_NAV,
             nav: float = C.NAV_THB, horizon: int = C.HORIZON_BARS,
             seed: int = C.SEED) -> tuple[pd.DataFrame, dict]:
    rng = np.random.default_rng(seed)
    idx = mk.close.index
    close, sigma, jump = mk.close.to_numpy(), mk.sigma.to_numpy(), mk.jump.to_numpy()
    observed = mk.observed.to_numpy()
    tickers = mk.tickers
    first, last = first_decision_bar(mk), len(idx) - 1 - horizon      # need bars t+1 … t+horizon
    if last < first:
        raise ValueError("not enough bars after the warm-up for one horizon")
    day_of_bar = idx.normalize()

    rejected = {"not_observed": 0, "jump": 0, "no_price": 0, "no_sigma": 0}
    base = []
    while len(base) < n_base:
        t = int(rng.integers(first, last + 1))
        j = int(rng.integers(len(tickers)))
        side = 1 if rng.random() < 0.5 else -1
        if not observed[t]:
            rejected["not_observed"] += 1
            continue
        if np.isnan(close[t: t + horizon + 1, j]).any():
            rejected["no_price"] += 1
            continue
        if jump[t: t + horizon + 1, j].any():
            rejected["jump"] += 1
            continue
        if not sigma[t, j] > 0:
            rejected["no_sigma"] += 1
            continue
        base.append((t, tickers[j], side))

    rows, oid = [], 1
    for b, (t, tk, side) in enumerate(base):
        arrival = float(close[t, tickers.index(tk)])
        adv = float(mk.adv.loc[day_of_bar[t], tk])
        for pct in buckets:
            qty = floor_lot(pct * nav / arrival)
            rows.append({"order_id": oid, "base_id": b, "ticker": tk, "side": side,
                         "bucket": f"{pct:.0%} NAV", "pct_nav": pct, "decision_i": t,
                         "decision_dt": idx[t], "year": int(idx[t].year), "hour": int(idx[t].hour),
                         "arrival_price": arrival, "qty": qty, "paper_notional": qty * arrival,
                         "adv": adv, "pct_adv": qty * arrival / adv,
                         "sigma": float(sigma[t, tickers.index(tk)])})
            oid += 1
    orders = pd.DataFrame(rows)
    info = {"n_base": n_base, "n_orders": len(orders), "rejected_draws": rejected,
            "first_decision_allowed": str(idx[first]), "last_decision_allowed": str(idx[last])}
    return orders, info
