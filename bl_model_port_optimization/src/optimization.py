"""
Module 6: Portfolio Optimization — Efficient Frontier + Max Sharpe
(bl_spec/06_PORTFOLIO_OPTIMIZATION.md)

Inputs μ_BL and Σ from M5 (both on the 63-day basis, 05 §7). Produces the full
efficient frontier (for plotting) and the Max-Sharpe weights w* (what M7 holds).
Long-only by default (09 §6); μ_BL feeds a standard mean-variance optimiser even
though it encodes relative views.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from . import constants as C


def _bounds(N: int, allow_short: bool):
    return None if allow_short else [(0.0, 1.0)] * N


def efficient_frontier(mu_BL: np.ndarray, Sigma: np.ndarray,
                       n_points: int = C.FRONTIER_POINTS,
                       allow_short: bool = C.ALLOW_SHORT) -> pd.DataFrame:
    """Trace min-variance portfolios across target returns. Infeasible targets
    near the extremes of μ_BL (under long-only) are skipped, not fatal."""
    N = len(mu_BL)
    targets = np.linspace(float(mu_BL.min()), float(mu_BL.max()), n_points)
    rows = []
    for r_target in targets:
        cons = [
            {"type": "eq", "fun": lambda w, rt=r_target: w @ mu_BL - rt},
            {"type": "eq", "fun": lambda w: np.sum(w) - 1.0},
        ]
        res = minimize(lambda w: w @ Sigma @ w, np.ones(N) / N,
                       method="SLSQP", bounds=_bounds(N, allow_short), constraints=cons)
        if res.success:
            vol = float(np.sqrt(res.x @ Sigma @ res.x))
            rows.append({"target_return": float(r_target), "volatility": vol,
                         "weights": res.x})
    return pd.DataFrame(rows)


def max_sharpe_portfolio(mu_BL: np.ndarray, Sigma: np.ndarray,
                         risk_free_rate: float = 0.0,
                         allow_short: bool = C.ALLOW_SHORT) -> np.ndarray:
    """w* maximising the Sharpe ratio. risk_free_rate must be in the SAME 63-day
    units as μ_BL (06 §4)."""
    N = len(mu_BL)

    def neg_sharpe(w):
        ret = w @ mu_BL
        vol = np.sqrt(w @ Sigma @ w)
        return -(ret - risk_free_rate) / vol if vol > 0 else 0.0

    cons = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]
    res = minimize(neg_sharpe, np.ones(N) / N, method="SLSQP",
                   bounds=_bounds(N, allow_short), constraints=cons)
    if not res.success:
        raise RuntimeError(f"Max Sharpe optimization failed: {res.message}")
    return res.x


def closed_form_weights(mu_BL: np.ndarray, Sigma: np.ndarray,
                        delta: float = C.BL_DELTA) -> np.ndarray:
    """Unconstrained w* = (δΣ)⁻¹μ_BL, renormalised. SANITY CHECK ONLY (06 §5) —
    may contain negative (short) weights even when long-only is intended."""
    w_raw = np.linalg.solve(delta * Sigma, mu_BL)
    return w_raw / np.sum(w_raw)


def annual_rf_to_horizon(rf_annual: float) -> float:
    """Convert an annualised risk-free rate to the 63-day equivalent (06 §4)."""
    return (1 + rf_annual) ** (C.HORIZON / C.TRADING_DAYS) - 1


def optimize(mu_BL: np.ndarray, Sigma: np.ndarray, stock_order: list[str],
             rf_annual: float = 0.0, build_frontier: bool = True) -> dict:
    """Module 6 output contract (06 §6): frontier + w_star + achieved Sharpe."""
    rf_h = annual_rf_to_horizon(rf_annual)
    w_star = max_sharpe_portfolio(mu_BL, Sigma, risk_free_rate=rf_h)
    vol = float(np.sqrt(w_star @ Sigma @ w_star))
    sharpe = float((w_star @ mu_BL - rf_h) / vol) if vol > 0 else float("nan")
    frontier = efficient_frontier(mu_BL, Sigma) if build_frontier else pd.DataFrame()
    return {
        "stock_order": stock_order,
        "frontier": frontier,
        "w_star": w_star,
        "w_star_sharpe": sharpe,
    }
