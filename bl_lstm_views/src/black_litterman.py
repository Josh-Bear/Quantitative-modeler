"""
black_litterman.py — the Black-Litterman core in pure numpy.

Ports zzz.py's run_bl and mirrors the policy already proven in the repo's JS engine
(black_litterman_model/engine/blacklitterman.js):

    Prior:           Π    = δ · Σ · w_mkt
    Posterior var:   M    = [(τΣ)⁻¹ + Pᵀ Ω⁻¹ P]⁻¹
    Posterior mean:  μ_BL = M · [(τΣ)⁻¹ Π + Pᵀ Ω⁻¹ Q]
    Total cov:       Σ_BL = Σ + M
    Optimal weight:  w*   = (δ · Σ_BL)⁻¹ · μ_BL   → long-only + cap → renormalise

Design choices kept consistent with the JS engine:
  • DIAG_EPS = 1e-4 added to Σ's diagonal before any inversion (near-singular guard).
  • optimalWeights returns RAW (un-normalised) weights; constrain_weights does the
    long-only clamp first, then normalises, then caps via iterative water-filling.
  • No views → w* collapses exactly to w_mkt (identity property).
"""
from __future__ import annotations

import numpy as np

from . import constants as C

DIAG_EPS = 1e-4


# ── inputs ───────────────────────────────────────────────────────────────────
def covariance(returns: np.ndarray, annualise: int = C.TRADING_DAYS) -> np.ndarray:
    """Annualised sample covariance from a (T, N) returns matrix."""
    return np.cov(returns, rowvar=False) * annualise


def market_weights(market_caps: np.ndarray) -> np.ndarray:
    """Cap-weighted w_mkt; falls back to equal weight if caps are missing/zero."""
    caps = np.asarray(market_caps, dtype=float)
    total = caps.sum()
    if total <= 0 or not np.isfinite(total):
        n = len(caps)
        return np.ones(n) / n
    return caps / total


def _regularize(sigma: np.ndarray, eps: float = DIAG_EPS) -> np.ndarray:
    return sigma + np.eye(sigma.shape[0]) * eps


# ── core ─────────────────────────────────────────────────────────────────────
def implied_returns(delta: float, sigma: np.ndarray, w_mkt: np.ndarray) -> np.ndarray:
    return delta * (sigma @ w_mkt)


def posterior(delta, tau, sigma, w_mkt, P, Q, omega):
    """Return (pi, mu_bl, sigma_bl). P:(k,N), Q:(k,), omega: (k,) diagonal variances."""
    sig = _regularize(sigma)
    pi = implied_returns(delta, sig, w_mkt)
    tau_sigma_inv = np.linalg.inv(tau * sig)

    if P is not None and len(P) > 0:
        P = np.asarray(P, dtype=float)
        Q = np.asarray(Q, dtype=float)
        omega_inv = np.linalg.inv(np.diag(np.asarray(omega, dtype=float)) + np.eye(len(omega)) * 1e-12)
        M = np.linalg.inv(tau_sigma_inv + P.T @ omega_inv @ P)
        mu_bl = M @ (tau_sigma_inv @ pi + P.T @ omega_inv @ Q)
    else:
        M = np.linalg.inv(tau_sigma_inv)
        mu_bl = pi.copy()

    return pi, mu_bl, sig + M


def optimal_weights_raw(delta: float, sigma_bl: np.ndarray, mu_bl: np.ndarray) -> np.ndarray:
    return np.linalg.inv(delta * sigma_bl) @ mu_bl


def constrain_weights(w_raw, long_only: bool = True,
                      min_w: float = C.MIN_WEIGHT, max_w: float = C.MAX_WEIGHT) -> np.ndarray:
    """Long-only clamp → normalise → per-asset min/max via iterative water-filling.
    Mirrors engine/blacklitterman.js constrainWeights()."""
    w = np.asarray(w_raw, dtype=float).copy()
    n = len(w)
    if long_only:
        w = np.maximum(w, 0.0)

    s = w.sum()
    w = w / s if s > 0 else np.ones(n) / n

    floor_w = min_w if n * min_w <= 1 else 0.0      # skip floor if infeasible
    cap_w = max(max_w, 1.0 / n)                      # can't cap below equal weight

    for _ in range(200):
        s = w.sum()
        w = w / s
        changed = False

        over = w > cap_w + 1e-9
        if over.any():
            excess = (w[over] - cap_w).sum()
            free_sum = w[~over].sum()
            if free_sum > 0:
                w[~over] = w[~over] + excess * (w[~over] / free_sum)
            w[over] = cap_w
            changed = True

        if floor_w > 0:
            under = w < floor_w - 1e-9
            if under.any():
                deficit = (floor_w - w[under]).sum()
                room_vals = np.maximum(w[~under] - floor_w, 0.0)
                room = room_vals.sum()
                if room > 0:
                    w[~under] = w[~under] - deficit * (room_vals / room)
                w[under] = floor_w
                changed = True

        if not changed:
            break

    s = w.sum()
    return w / s if s > 0 else w


def leverage(w_raw: np.ndarray) -> float:
    """Gross leverage Σ|wᵢ| of the normalised raw weights ( >1 ⇒ wanted shorts )."""
    total = w_raw.sum() or 1.0
    return float(np.abs(w_raw / total).sum())


def solve(sigma, w_mkt, *, delta=C.BL_DELTA, tau=C.BL_TAU, P=None, Q=None, omega=None,
          max_weight=C.MAX_WEIGHT, min_weight=C.MIN_WEIGHT) -> dict:
    """Full BL solve → dict(pi, mu_bl, w_raw, w_star, leverage). No views ⇒ w*=w_mkt."""
    if P is None or len(P) == 0:
        pi = implied_returns(delta, _regularize(sigma), w_mkt)
        return {"pi": pi, "mu_bl": pi.copy(), "w_raw": w_mkt.copy(),
                "w_star": w_mkt.copy(), "leverage": 1.0}

    pi, mu_bl, sigma_bl = posterior(delta, tau, sigma, w_mkt, P, Q, omega)
    w_raw = optimal_weights_raw(delta, sigma_bl, mu_bl)
    w_star = constrain_weights(w_raw, long_only=True, min_w=min_weight, max_w=max_weight)
    return {"pi": pi, "mu_bl": mu_bl, "w_raw": w_raw,
            "w_star": w_star, "leverage": leverage(w_raw)}


# ── analytics ────────────────────────────────────────────────────────────────
def portfolio_return(w: np.ndarray, mu: np.ndarray) -> float:
    return float(np.dot(w, mu))


def portfolio_vol(w: np.ndarray, sigma: np.ndarray) -> float:
    return float(np.sqrt(max(w @ sigma @ w, 0.0)))


def sharpe(w, mu, sigma, rf: float = C.RISK_FREE) -> float:
    vol = portfolio_vol(w, sigma)
    return (portfolio_return(w, mu) - rf) / vol if vol > 0 else 0.0


def tracking_error(w, w_mkt, sigma) -> float:
    active = np.asarray(w) - np.asarray(w_mkt)
    return float(np.sqrt(max(active @ sigma @ active, 0.0)))
