"""
Module 4: Stock Selection — the 22-stock universe (bl_spec/04_STOCK_SELECTION.md)

At each rebalance date, reduce the full universe to the top-2 stocks (by a
risk-adjusted score — see OMEGA_FLOOR / select_universe below, a deviation from
the spec's raw-r_hat ranking) in each of the 11 GICS sectors → up to 22 stocks.
Dynamic: re-computed every rebalance, the specific tickers change over time.
"""
from __future__ import annotations

import warnings
from typing import Optional

import numpy as np
import pandas as pd

from . import constants as C

# DEVIATION from bl_spec/04_STOCK_SELECTION.md §2 (ranks by raw r_hat) — approved
# by Josh 2026-07-02. This project's own ML diagnostics (output/report, mean IC
# ~0.086) showed the per-stock predictions are only weakly predictive per the
# spec's own threshold (08 §4.1), so ranking 500 noisy point-estimates by raw
# r_hat and cutting exactly at rank 2 lets estimation noise — not genuine skill —
# decide sector membership. See bl_spec/09_OPEN_DECISIONS.md §11.
OMEGA_FLOOR = 1e-8   # avoid /0 on a near-perfect validation fit (mirrors M5's floor)


def select_universe(predictions: pd.DataFrame, sector_map: dict) -> pd.DataFrame:
    """Top-N per sector by a RISK-ADJUSTED score, not raw r_hat (see module-level
    deviation note above). Returns [ticker, sector, r_hat, omega, score,
    rank_in_sector]; rank 1 = sector "top", rank 2 = sector "2nd" (used by M5 for
    the relative views).

    score = r_hat / sqrt(omega) — a t-stat-like measure. A high r_hat backed by a
    noisy (high-omega) prediction is discounted; a smaller r_hat the model is
    confident about (low omega) is favoured. Only the SELECTION criterion changes
    — Q (the view return M5 feeds to Black-Litterman) is still the raw r_hat, so
    the economic meaning of the view is untouched.
    """
    df = predictions.copy()
    df["sector"] = df["ticker"].map(sector_map)
    df = df.dropna(subset=["sector"])

    # 04 §3.3 — drop failed predictions before ranking; log the count.
    n_before = len(df)
    df = df.dropna(subset=["r_hat"])
    dropped = n_before - len(df)
    if dropped:
        print(f"[M4] dropped {dropped} stocks with NaN r_hat before ranking.")

    safe_omega = df["omega"].clip(lower=OMEGA_FLOOR)
    df["score"] = df["r_hat"] / np.sqrt(safe_omega)

    # 04 §3.2 — method='first' breaks ties deterministically by input order.
    df["rank_in_sector"] = (df.groupby("sector")["score"]
                              .rank(ascending=False, method="first"))

    selected = df[df["rank_in_sector"] <= C.N_PER_SECTOR].copy()
    selected = selected.sort_values(["sector", "rank_in_sector"]).reset_index(drop=True)

    _warn_thin_sectors(selected)
    return selected[["ticker", "sector", "r_hat", "omega", "score", "rank_in_sector"]]


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
