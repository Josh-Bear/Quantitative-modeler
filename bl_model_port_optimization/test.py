"""
test.py — network-free sanity checks for the deterministic core
(M4 selection, M5 Black-Litterman, M6 optimization, M8 metrics).

Mirrors bl_lstm_views/test.py: no yfinance, no torch training, no disk — just the
numeric guarantees the spec calls out. Run with:  python test.py
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from src import constants as C
from src import selection as sel
from src import black_litterman as bl
from src import optimization as opt
from src import evaluation as ev

_fail = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global _fail
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        _fail += 1


def _toy_universe() -> pd.DataFrame:
    return pd.DataFrame({
        "ticker": ["A1", "A2", "B1", "B2"],
        "sector": ["Energy", "Energy", "Tech", "Tech"],
        "r_hat": [0.10, 0.04, 0.08, 0.05],
        "omega": [0.02, 0.03, 0.015, 0.02],
        "rank_in_sector": [1, 2, 1, 2],
    })


def _toy_sigma(n=4, seed=0):
    rng = np.random.default_rng(seed)
    A = rng.normal(size=(n, n))
    return A @ A.T * 0.01


def test_selection():
    print("M4 selection:")
    preds = pd.DataFrame({
        "ticker": ["A1", "A2", "A3", "B1", "B2"],
        "r_hat": [0.1, 0.2, 0.05, 0.08, 0.03],
        "omega": [0.02] * 5,
    })
    smap = {"A1": "Energy", "A2": "Energy", "A3": "Energy", "B1": "Tech", "B2": "Tech"}
    u = sel.select_universe(preds, smap)
    check("top-2 per sector", len(u) == 4)
    energy_top = u[(u.sector == "Energy") & (u.rank_in_sector == 1)].iloc[0]["ticker"]
    check("highest r_hat ranked #1", energy_top == "A2", f"got {energy_top}")
    turn = sel.compute_universe_turnover({"A2", "B1"}, {"A2", "B2"})
    check("turnover entered/exited", turn["entered"] == {"B2"} and turn["exited"] == {"B1"})


def test_bl():
    print("M5 Black-Litterman:")
    u = _toy_universe()
    order = bl.make_stock_order(u)
    P, Q, na, nr = bl.construct_P_Q(u, order)
    check("4 views (2 abs + 2 rel)", P.shape == (4, 4) and na == 2 and nr == 2)
    check("absolute block first (one-hot rows)",
          np.array_equal(P[:2], np.array([[1, 0, 0, 0], [0, 0, 1, 0]])))
    check("relative block (long-short rows)",
          np.array_equal(P[2:], np.array([[1, -1, 0, 0], [0, 0, 1, -1]])))
    check("Q relative = top - 2nd", np.isclose(Q[2], 0.06) and np.isclose(Q[3], 0.03))

    Sigma = _toy_sigma()
    tau_sigma = C.BL_TAU * Sigma
    Om = bl.construct_omega(u["omega"].to_numpy(), P, tau_sigma, na)
    abs_scale = np.diag(Om)[:na].mean()
    rel_scale = np.diag(Om)[na:].mean()
    check("two-scale Ω (abs != rel block)", not np.isclose(abs_scale, rel_scale))

    w_mkt = np.array([0.3, 0.2, 0.3, 0.2])
    Pi = bl.compute_prior(Sigma, w_mkt)
    # no-views posterior must equal the prior (BL identity)
    tsi = np.linalg.inv(tau_sigma)
    mu_noviews = np.linalg.solve(tsi, tsi @ Pi)
    check("no-views posterior == prior", np.allclose(mu_noviews, Pi))
    mu = bl.compute_bl_posterior(Sigma, Pi, P, Q, Om)
    check("posterior finite & right shape", mu.shape == (4,) and np.isfinite(mu).all())


def test_optimization():
    print("M6 optimization:")
    Sigma = _toy_sigma()
    mu = np.array([0.05, 0.01, 0.04, 0.02])
    w = opt.max_sharpe_portfolio(mu, Sigma)
    check("w sums to 1", np.isclose(w.sum(), 1.0))
    check("long-only (w >= 0)", (w >= -1e-9).all())
    fr = opt.efficient_frontier(mu, Sigma, n_points=20)
    check("frontier non-empty & vol > 0", len(fr) > 0 and (fr["volatility"] > 0).all())
    rf_h = opt.annual_rf_to_horizon(0.05)
    check("rf annual->63d in (0, annual)", 0 < rf_h < 0.05)


def test_metrics():
    print("M8 metrics:")
    # four quarters of +5% → annualised return ~ (1.05^4 - 1)
    r = pd.Series([0.05, 0.05, 0.05, 0.05])
    pv = (1 + r).cumprod()
    check("annualised return of 5%/q", np.isclose(ev.annualized_return(r), 1.05 ** 4 - 1))
    check("max drawdown 0 on monotonic up", np.isclose(ev.max_drawdown(pv), 0.0))
    r2 = pd.Series([0.1, -0.2, 0.15, -0.05])
    pv2 = (1 + r2).cumprod()
    check("max drawdown negative on a dip", ev.max_drawdown(pv2) < 0)
    check("VaR(95) <= median", ev.value_at_risk(r2) <= r2.median())


def test_transaction_cost():
    print("M7 transaction cost:")
    from src import backtest as bt
    # full liquidation + full re-buy of a disjoint book → turnover 2.0 → cost 2*rate
    cost = bt.compute_transaction_cost({"A": 1.0}, {"B": 1.0}, cost_rate=0.001)
    check("disjoint rebalance turnover = 2", np.isclose(cost, 0.002))
    cost2 = bt.compute_transaction_cost({"A": 0.5, "B": 0.5}, {"A": 0.5, "B": 0.5})
    check("no change → zero cost", np.isclose(cost2, 0.0))


def main() -> int:
    print("=== network-free core checks ===")
    test_selection()
    test_bl()
    test_optimization()
    test_metrics()
    test_transaction_cost()
    print(f"\n{'ALL PASSED' if _fail == 0 else str(_fail) + ' CHECK(S) FAILED'}")
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
