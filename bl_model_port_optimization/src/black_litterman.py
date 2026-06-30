"""
Module 5: Black-Litterman — P, Q, Ω construction + posterior
(bl_spec/05_BL_MODEL.md)

Given the 22 selected stocks (r_hat, omega, rank_in_sector) build the BL inputs,
combine with the market-implied prior, and return the posterior μ_BL.

UNIT CONSISTENCY (05 §7) — the single most likely silent bug. Q is in 63-day
return units (the SVR target). Σ is built from DAILY returns, so it is scaled by
HORIZON (×63) ONCE here and that 63-day Σ is used everywhere downstream (Π, τΣ,
and M6's optimisation / risk-free conversion). Never mix daily-Σ with 63-day-Q.

View block ordering (05 §4 + §5): all absolute views FIRST (rows 0..n_abs-1),
then all relative views. construct_omega's abs/rel masks rely on this block
layout, so do not interleave.
"""
from __future__ import annotations

import os
import warnings
from typing import Optional

import numpy as np
import pandas as pd

from . import constants as C
from . import data_pipeline as dp


# ─────────────────────────────────────────────────────────────────────────────
# Ordering — one fixed stock_order threaded through P, Q, Σ, Ω, w  (05 §4)
# ─────────────────────────────────────────────────────────────────────────────
def make_stock_order(universe_df: pd.DataFrame) -> list[str]:
    """Fixed 0..N-1 ordering: by sector name, then rank_in_sector."""
    ordered = universe_df.sort_values(["sector", "rank_in_sector"])
    return ordered["ticker"].tolist()


# ─────────────────────────────────────────────────────────────────────────────
# Step 1 — Σ  (05 §3, §7)
# ─────────────────────────────────────────────────────────────────────────────
def load_returns_window(stock_order: list[str], reb_date) -> pd.DataFrame:
    """Daily returns for the 22 tickers over the SAME rolling 10-year window the
    ML model trains on (05 §3 — consistency is intentional), strictly < reb_date.
    Columns are in stock_order; rows with any missing ticker are dropped."""
    reb_ts = pd.Timestamp(reb_date)
    win_start = reb_ts - pd.DateOffset(years=C.ROLLING_WINDOW_YEARS)
    cols = {}
    for t in stock_order:
        s = dp.load_close_series(t)
        if s is None:
            continue
        s = s[(s.index >= win_start) & (s.index < reb_ts)]
        cols[t] = s.pct_change()
    rets = pd.DataFrame(cols).dropna(how="any")
    return rets[[t for t in stock_order if t in rets.columns]]


def compute_covariance(returns_df: pd.DataFrame) -> np.ndarray:
    """Daily covariance scaled to the 63-day horizon (05 §7). Variance scales
    linearly with time under the random-walk assumption."""
    sigma_daily = returns_df.cov().values
    return sigma_daily * C.HORIZON_SCALE


# ─────────────────────────────────────────────────────────────────────────────
# Step 2 — P (view matrix) and Q (view returns)  (05 §4)
# ─────────────────────────────────────────────────────────────────────────────
def construct_P_Q(universe_df: pd.DataFrame, stock_order: list[str]) -> tuple:
    """Return (P, Q, n_absolute, n_relative). Block layout: all absolute views
    first, then all relative views."""
    idx = {t: i for i, t in enumerate(stock_order)}
    N = len(stock_order)

    abs_rows, abs_q, rel_rows, rel_q = [], [], [], []
    # iterate sectors in the same (sector, rank) order as stock_order
    for sector, grp in universe_df.sort_values(["sector", "rank_in_sector"]).groupby("sector"):
        top = grp[grp["rank_in_sector"] == 1]
        second = grp[grp["rank_in_sector"] == 2]
        if len(top) == 0:
            continue  # defensive — M4 guarantees a top per non-empty sector
        i = idx[top.iloc[0]["ticker"]]

        # Absolute view on the top stock
        r = np.zeros(N); r[i] = 1.0
        abs_rows.append(r); abs_q.append(float(top.iloc[0]["r_hat"]))

        # Relative view top − 2nd (skipped if the sector had only 1 candidate, 05 §4)
        if len(second) > 0:
            j = idx[second.iloc[0]["ticker"]]
            r2 = np.zeros(N); r2[i] = 1.0; r2[j] = -1.0
            rel_rows.append(r2)
            rel_q.append(float(top.iloc[0]["r_hat"]) - float(second.iloc[0]["r_hat"]))

    P = np.array(abs_rows + rel_rows)
    Q = np.array(abs_q + rel_q)
    return P, Q, len(abs_rows), len(rel_rows)


# ─────────────────────────────────────────────────────────────────────────────
# Step 3 — Ω with TWO separate scale factors  (05 §5 — never a single global scale)
# ─────────────────────────────────────────────────────────────────────────────
def construct_omega(omega_by_order: np.ndarray, P: np.ndarray,
                    tau_sigma: np.ndarray, n_absolute: int) -> np.ndarray:
    """Diagonal Ω. raw[k] = ω_i for an absolute view, ω_i+ω_j for a relative view
    (the difference of two independent-ish errors). Absolute and relative blocks
    are calibrated with SEPARATE scale factors so neither systematically dominates
    the BL posterior (05 §5 — explicitly decided; do not collapse to one scale)."""
    K = P.shape[0]
    raw = np.array([omega_by_order[np.nonzero(P[k])[0]].sum() for k in range(K)])
    raw = np.maximum(raw, 1e-12)  # floor: a near-perfect val fit must not give Ω=0

    abs_mask = np.arange(K) < n_absolute
    rel_mask = ~abs_mask
    diag_tau_sigma = np.diag(tau_sigma)

    # Absolute: match the median diagonal of τΣ.
    alpha_abs = (np.median(diag_tau_sigma) / np.median(raw[abs_mask])
                 if abs_mask.any() else 1.0)
    # Relative: match the τΣ-implied variance of each long-short pair, P_k τΣ P_kᵀ.
    if rel_mask.any():
        rel_implied = np.array([P[k] @ tau_sigma @ P[k].T
                                for k in range(K) if rel_mask[k]])
        alpha_rel = np.median(rel_implied) / np.median(raw[rel_mask])
    else:
        alpha_rel = 1.0

    calibrated = raw.copy()
    calibrated[abs_mask] *= alpha_abs
    calibrated[rel_mask] *= alpha_rel
    return np.diag(calibrated)


# ─────────────────────────────────────────────────────────────────────────────
# Step 4 — Prior Π  (05 §6)
# ─────────────────────────────────────────────────────────────────────────────
def compute_prior(Sigma: np.ndarray, w_mkt: np.ndarray, delta: float = C.BL_DELTA) -> np.ndarray:
    """Π = δ Σ w_mkt (same 63-day units as Σ)."""
    return delta * Sigma @ w_mkt


def market_weights(stock_order: list[str], reb_date) -> np.ndarray:
    """Market-cap weights of the 22 stocks as of reb_date, renormalised to sum to
    1 within the subset (05 §6). Missing caps fall back to the mean of present
    caps so a stock is not silently zero-weighted."""
    mcap_path = os.path.join(C.REFERENCE_DIR, "mcap_history.parquet")
    reb_ts = pd.Timestamp(reb_date)
    caps = np.full(len(stock_order), np.nan)
    if os.path.exists(mcap_path):
        mh = pd.read_parquet(mcap_path)
        mh["date"] = pd.to_datetime(mh["date"])
        mh = mh[mh["date"] < reb_ts]
        latest = (mh.sort_values("date").groupby("ticker")["market_cap"].last())
        for i, t in enumerate(stock_order):
            if t in latest.index:
                caps[i] = latest[t]
    if np.isnan(caps).all():
        warnings.warn("[M5] no market caps available — using equal weights.")
        return np.ones(len(stock_order)) / len(stock_order)
    fill = np.nanmean(caps)
    caps = np.where(np.isnan(caps), fill, caps)
    return caps / caps.sum()


# ─────────────────────────────────────────────────────────────────────────────
# Step 5 — Posterior μ_BL  (05 §8)
# ─────────────────────────────────────────────────────────────────────────────
def compute_bl_posterior(Sigma: np.ndarray, Pi: np.ndarray, P: np.ndarray,
                         Q: np.ndarray, Omega: np.ndarray, tau: float = C.BL_TAU) -> np.ndarray:
    """μ_BL = [(τΣ)⁻¹ + PᵀΩ⁻¹P]⁻¹ [(τΣ)⁻¹Π + PᵀΩ⁻¹Q], solved (not inverted)."""
    tau_sigma_inv = np.linalg.inv(tau * Sigma)
    omega_inv = np.linalg.inv(Omega)
    A = tau_sigma_inv + P.T @ omega_inv @ P
    b = tau_sigma_inv @ Pi + P.T @ omega_inv @ Q
    return np.linalg.solve(A, b)


# ─────────────────────────────────────────────────────────────────────────────
# Numerical stability  (05 §9)
# ─────────────────────────────────────────────────────────────────────────────
def stabilize_sigma(Sigma: np.ndarray) -> np.ndarray:
    """Add a small ridge if Σ is ill-conditioned (likely with 22 correlated
    stocks from 11 sectors over only 10 years)."""
    cond = np.linalg.cond(Sigma)
    if cond > C.COND_WARN:
        eps = C.RIDGE_EPS * np.trace(Sigma) / Sigma.shape[0]
        warnings.warn(f"[M5] cond(Σ)={cond:.2e} > {C.COND_WARN:.0e}; adding ridge "
                      f"{eps:.2e}·I (05 §9).")
        return Sigma + eps * np.eye(Sigma.shape[0])
    return Sigma


def _sanity_check_mu(mu_BL: np.ndarray, Q: np.ndarray, Pi: np.ndarray, reb_date) -> None:
    bound = 5 * max(np.abs(Q).max(initial=0.0), np.abs(Pi).max(initial=0.0))
    if bound > 0 and np.abs(mu_BL).max() > bound:
        warnings.warn(f"[M5] μ_BL at {reb_date} exceeds 5× the input view/prior "
                      f"range ({np.abs(mu_BL).max():.3f} > {bound:.3f}) — possible "
                      f"unit mismatch or numerical issue (05 §9).")


# ─────────────────────────────────────────────────────────────────────────────
# Orchestration — Module 5 output contract (05 §10)
# ─────────────────────────────────────────────────────────────────────────────
def compute_bl_pipeline(universe_df: pd.DataFrame, reb_date) -> Optional[dict]:
    """Full M5: Σ → P,Q → Ω → Π → μ_BL for one rebalance date."""
    stock_order = make_stock_order(universe_df)

    rets = load_returns_window(stock_order, reb_date)
    stock_order = list(rets.columns)            # keep only tickers with returns
    if len(stock_order) < 2:
        warnings.warn(f"[M5] <2 stocks with returns at {reb_date} — skipping BL.")
        return None
    universe_df = (universe_df.set_index("ticker").loc[stock_order].reset_index())

    Sigma = stabilize_sigma(compute_covariance(rets))      # 63-day units
    w_mkt = market_weights(stock_order, reb_date)
    Pi = compute_prior(Sigma, w_mkt)

    P, Q, n_abs, n_rel = construct_P_Q(universe_df, stock_order)
    omega_by_order = universe_df["omega"].to_numpy(dtype="float64")
    tau_sigma = C.BL_TAU * Sigma
    Omega = construct_omega(omega_by_order, P, tau_sigma, n_abs)

    mu_BL = compute_bl_posterior(Sigma, Pi, P, Q, Omega)
    _sanity_check_mu(mu_BL, Q, Pi, reb_date)

    return {
        "rebalance_date": pd.Timestamp(reb_date),
        "stock_order": stock_order,
        "mu_BL": mu_BL,
        "Sigma": Sigma,
        "Pi": Pi,
        "w_mkt": w_mkt,
        "P": P, "Q": Q, "Omega": Omega,
        "n_absolute_views": n_abs,
        "n_relative_views": n_rel,
    }
