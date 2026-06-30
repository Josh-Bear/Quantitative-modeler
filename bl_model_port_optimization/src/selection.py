"""
Module 4: Stock Selection — the 22-stock universe (bl_spec/04_STOCK_SELECTION.md)

At each rebalance date, reduce the full universe to the top-2 stocks (by predicted
return) in each of the 11 GICS sectors → up to 22 stocks. Dynamic: re-computed
every rebalance, the specific tickers change over time.
"""
from __future__ import annotations

import warnings
from typing import Optional

import numpy as np
import pandas as pd

from . import constants as C


def select_universe(predictions: pd.DataFrame, sector_map: dict) -> pd.DataFrame:
    """Top-N per sector by r_hat. Returns [ticker, sector, r_hat, omega,
    rank_in_sector]; rank 1 = sector "top", rank 2 = sector "2nd" (used by M5
    for the relative views)."""
    df = predictions.copy()
    df["sector"] = df["ticker"].map(sector_map)
    df = df.dropna(subset=["sector"])

    # 04 §3.3 — drop failed predictions before ranking; log the count.
    n_before = len(df)
    df = df.dropna(subset=["r_hat"])
    dropped = n_before - len(df)
    if dropped:
        print(f"[M4] dropped {dropped} stocks with NaN r_hat before ranking.")

    # 04 §3.2 — method='first' breaks ties deterministically by input order.
    df["rank_in_sector"] = (df.groupby("sector")["r_hat"]
                              .rank(ascending=False, method="first"))

    selected = df[df["rank_in_sector"] <= C.N_PER_SECTOR].copy()
    selected = selected.sort_values(["sector", "rank_in_sector"]).reset_index(drop=True)

    _warn_thin_sectors(selected)
    return selected[["ticker", "sector", "r_hat", "omega", "rank_in_sector"]]


def _warn_thin_sectors(selected: pd.DataFrame) -> None:
    """04 §3.1 — log sectors that produced <2 candidates (graceful degrade)."""
    counts = selected.groupby("sector")["ticker"].count()
    for sector in C.GICS_SECTORS:
        c = int(counts.get(sector, 0))
        if c == 0:
            warnings.warn(f"[M4] sector '{sector}' has 0 candidates — excluded "
                          f"this rebalance (universe < 22).")
        elif c < C.N_PER_SECTOR:
            warnings.warn(f"[M4] sector '{sector}' has only {c} candidate — "
                          f"absolute view only, relative view skipped (04 §3.1).")


def compute_universe_turnover(prev_universe: Optional[set], new_universe: set) -> dict:
    """04 §4 — track how the 22-stock set changes (feeds M7 costs + M8 reporting).
    `entered`/`exited` are full buys/sells; `overlap_pct` is None on the first
    rebalance."""
    prev = prev_universe or set()
    entered = new_universe - prev
    exited = prev - new_universe
    overlap_pct = (len(prev & new_universe) / len(prev)) if prev else None
    return {"entered": entered, "exited": exited, "overlap_pct": overlap_pct}
