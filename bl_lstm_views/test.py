"""
test.py — fast, network-free sanity checks for the numpy Black-Litterman core.

Reproduces zzz.py's mock-data setup and asserts the two invariants the JS engine
also guarantees:
  1. No views  → w* == w_mkt   (posterior collapses to the prior).
  2. Constraints hold: long-only, per-asset cap, weights sum to 1.

Run:  python test.py
"""
import numpy as np

from src import black_litterman as bl
from src import constants as C


def _mock_sigma_and_caps():
    np.random.seed(42)
    true_vol = np.array([0.120, 0.065, 0.070, 0.085])
    corr = np.array([
        [1.00, 0.45, 0.42, 0.48],
        [0.45, 1.00, 0.75, 0.70],
        [0.42, 0.75, 1.00, 0.68],
        [0.48, 0.70, 0.68, 1.00],
    ])
    sigma = np.diag(true_vol) @ corr @ np.diag(true_vol)
    caps = np.array([5.10, 3.20, 2.81, 4.44])
    return sigma, caps


def test_no_views_identity():
    sigma, caps = _mock_sigma_and_caps()
    w_mkt = bl.market_weights(caps)
    res = bl.solve(sigma, w_mkt, delta=3.0, tau=0.05)  # no P/Q/omega
    assert np.allclose(res["w_star"], w_mkt, atol=1e-10), res["w_star"]
    print("  ✅ no-views identity: w* == w_mkt")


def test_constraints_hold():
    sigma, caps = _mock_sigma_and_caps()
    w_mkt = bl.market_weights(caps)
    P = np.array([[1.0, 0.0, -1.0, 0.0],   # asset0 > asset2
                  [0.0, 0.0, 0.0, 1.0]])    # asset3 absolute
    Q = np.array([0.05, 0.18])
    omega = np.array([0.001, 0.0005])
    res = bl.solve(sigma, w_mkt, delta=3.0, tau=0.05, P=P, Q=Q, omega=omega,
                   max_weight=0.40, min_weight=0.0)
    w = res["w_star"]
    assert abs(w.sum() - 1.0) < 1e-9, w.sum()
    assert np.all(w >= -1e-9), w
    assert np.all(w <= 0.40 + 1e-9), w
    print(f"  ✅ constraints hold: w*={np.round(w, 4)} sum={w.sum():.6f}")


def test_implied_returns_sign():
    sigma, caps = _mock_sigma_and_caps()
    w_mkt = bl.market_weights(caps)
    pi = bl.implied_returns(C.BL_DELTA, sigma, w_mkt)
    assert np.all(pi > 0), pi  # long market, positive-definite Σ → positive implied returns
    print(f"  ✅ implied returns positive: Π={np.round(pi, 4)}")


if __name__ == "__main__":
    print("BL core sanity checks")
    test_no_views_identity()
    test_constraints_hold()
    test_implied_returns_sign()
    print("All passed.")
