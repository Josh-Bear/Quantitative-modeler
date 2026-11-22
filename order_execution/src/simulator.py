"""
simulator.py — hourly event loop. One independent portfolio per strategy, all
fed by the same price path and the same signal stream.

At each bar i (decision at the close):
  a) work parent orders opened in earlier bars (sells first)
                                   → fills at Close_i ± cost, capped by bar i's traded value
  b) pre-trade: signals at Close_i → checked order requests
  c) open new parent orders (arrival = Close_i); their first slice fills in bar i+1
  d) mark NAV = cash + Σ shares × Close_i
Open orders left at the end of the data are cancelled at the last close.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import constants as C
from .data_loader import MarketData
from .execution import ParentOrder, execute_bar
from .market_rules import floor_lot
from .pretrade import generate_orders


def rolling_sigma(prices: pd.DataFrame) -> pd.DataFrame:
    ret = prices.pct_change()
    sig = ret.rolling(C.SIGMA_LEN, min_periods=20).std()
    return sig.fillna(ret.expanding(min_periods=2).std()).fillna(0.0)


def initial_portfolio(prices: pd.DataFrame) -> tuple[dict[str, int], float]:
    tickers = list(prices.columns)
    p0 = prices.iloc[0]
    if C.INITIAL_WEIGHTS:
        weights = {t: C.INITIAL_WEIGHTS.get(t, 0.0) for t in tickers}
    else:
        w = (1.0 - C.INITIAL_CASH_PCT) / len(tickers)
        weights = {t: w for t in tickers}
    holdings = {t: floor_lot(weights[t] * C.INITIAL_NAV / p0[t]) for t in tickers}
    cash = C.INITIAL_NAV - sum(holdings[t] * p0[t] for t in tickers)
    return holdings, cash


def run_strategy(md: MarketData, sig: dict[str, pd.DataFrame], strategy: str,
                 n_slices: int, sigma: pd.DataFrame | None = None) -> dict:
    prices = md.close
    tickers = list(prices.columns)
    sigma = rolling_sigma(prices) if sigma is None else sigma
    P, S, V = prices.to_numpy(), sigma.to_numpy(), md.value.to_numpy()
    codes = np.column_stack([sig[t]["signal_code"].to_numpy() for t in tickers])
    dws = np.column_stack([sig[t]["dw"].to_numpy() for t in tickers])

    holdings, cash = initial_portfolio(prices)
    orders: list[ParentOrder] = []
    open_by_ticker: dict[str, ParentOrder] = {}
    fills: list[dict] = []
    log: list[dict] = []
    nav_rows = []
    next_id = 1

    def work(order: ParentOrder, i: int, dt):
        nonlocal cash
        j = tickers.index(order.ticker)
        f = execute_bar(order, i, dt, P[i, j], S[i, j], cash, V[i, j])
        if f is not None:
            holdings[order.ticker] += order.side * f["qty"]
            cash += f["cash_flow"]
            f["cash_after"] = cash
            fills.append(f)
        if order.status != "OPEN":
            open_by_ticker.pop(order.ticker, None)

    for i, dt in enumerate(prices.index):
        # a) open orders, sells first
        for o in sorted(open_by_ticker.values(), key=lambda o: o.side):
            work(o, i, dt)

        # b) pre-trade
        row = {t: P[i, j] for j, t in enumerate(tickers)}
        reqs = generate_orders(dt, strategy, tickers, row,
                               {t: int(codes[i, j]) for j, t in enumerate(tickers)},
                               {t: float(dws[i, j]) for j, t in enumerate(tickers)},
                               holdings, cash,
                               {t: o.side * o.remaining for t, o in open_by_ticker.items()}, log)

        # c) new parent orders — worked from bar i+1
        for r in reqs:
            o = ParentOrder(next_id, strategy, r.ticker, r.side, r.qty, r.reason, i, dt,
                            row[r.ticker], r.current_w, r.target_w, n_slices)
            next_id += 1
            orders.append(o)
            open_by_ticker[r.ticker] = o

        # d) mark to market
        pos_val = {t: holdings[t] * row[t] for t in tickers}
        nav = cash + sum(pos_val.values())
        nav_rows.append({"datetime": dt, "cash": cash, "positions": nav - cash, "nav": nav,
                         **{f"w_{t}": pos_val[t] / nav for t in tickers},
                         **{f"sh_{t}": holdings[t] for t in tickers}})

    last_i = len(prices) - 1
    for o in list(open_by_ticker.values()):
        o.cancel(last_i, P[last_i, tickers.index(o.ticker)], "end of data")

    return {"strategy": strategy, "n_slices": n_slices, "orders": orders, "fills": fills,
            "pretrade_log": log, "nav": pd.DataFrame(nav_rows).set_index("datetime"),
            "final_holdings": dict(holdings), "final_cash": cash}


def run_all(md: MarketData, sig: dict[str, pd.DataFrame],
            strategies: dict[str, int] = C.STRATEGIES) -> dict[str, dict]:
    sigma = rolling_sigma(md.close)
    return {name: run_strategy(md, sig, name, n, sigma) for name, n in strategies.items()}
