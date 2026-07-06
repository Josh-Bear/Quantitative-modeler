"""
backtest.py — walk-forward backtest of the BL+model portfolio over the test year.

Every HORIZON trading days we stand on a date t, read each stock's model view
(q = annualised expected return implied by the LSTM+SVR price forecast), run the BL
solve to get optimal weights w*, and hold them until the next rebalance. Realised
returns come from actual closes. The strategy is compared to SPY buy-&-hold on the
same rebalance grid, using the paper's metrics (eqs. 9–10):

    annual return, Sharpe ratio (net of risk-free), maximum drawdown.

Σ is estimated once from pre-test (train+val) daily returns — a standard, look-ahead-
free simplification. The trained models/SVR from views.py are reused (no retraining).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import black_litterman as bl
from . import constants as C
from .svr_model import predict_price

ANN = C.TRADING_DAYS / C.HORIZON


def _close_panel(stock_data: dict, tickers: list[str]) -> pd.DataFrame:
    cols = {t: pd.Series(stock_data[t].close_raw,
                         index=pd.DatetimeIndex(stock_data[t].dates).normalize())
            for t in tickers}
    return pd.DataFrame(cols).dropna()


def _q_lookup(stock_data: dict, views: dict, ticker: str) -> dict:
    """Map each test as-of date → annualised view return for one stock."""
    sd = stock_data[ticker]
    lstm = views["per_stock"][ticker]["_lstm"]
    svr = views["per_stock"][ticker]["_svr"]
    if lstm["test_pred"].shape[0] == 0:
        return {}
    ref_asof = sd.ref_raw[lstm["test_asof_idx"]]
    pred_price = predict_price(svr, sd, lstm["test_pred"], ref_asof)
    close_asof = sd.close_raw[lstm["test_asof_idx"]]
    q_h = np.clip((pred_price - close_asof) / close_asof, -C.VIEW_Q_CAP, C.VIEW_Q_CAP)
    q_ann = q_h * ANN
    dates = pd.DatetimeIndex(lstm["test_asof_dates"]).normalize()
    return dict(zip(dates, q_ann))


def _metrics(period_returns: np.ndarray, periods_per_year: float,
             rf: float = C.RISK_FREE) -> dict:
    r = np.asarray(period_returns, dtype=float)
    if r.size == 0:
        return {"ann_return": float("nan"), "ann_vol": float("nan"),
                "sharpe": float("nan"), "max_drawdown": float("nan"),
                "cum_return": float("nan")}
    equity = np.cumprod(1.0 + r)
    cum = float(equity[-1] - 1.0)
    n_years = r.size / periods_per_year
    ann_return = (1.0 + cum) ** (1.0 / n_years) - 1.0 if n_years > 0 else float("nan")
    ann_vol = float(r.std(ddof=0) * np.sqrt(periods_per_year))
    sharpe = (ann_return - rf) / ann_vol if ann_vol > 0 else float("nan")
    drawdown = equity / np.maximum.accumulate(equity) - 1.0
    return {"ann_return": ann_return, "ann_vol": ann_vol, "sharpe": sharpe,
            "max_drawdown": float(drawdown.min()), "cum_return": cum}


def run_backtest(stock_data: dict, views: dict, w_mkt: np.ndarray,
                 benchmark_close: pd.Series | None,
                 max_weight: float = C.MAX_WEIGHT,
                 min_weight: float = C.MIN_WEIGHT) -> dict:
    tickers = views["tickers"]
    panel = _close_panel(stock_data, tickers)

    # Σ from pre-test daily returns (train + val = everything before the fixed test window)
    rets = panel.pct_change().dropna()
    pre_end = max(0, len(rets) - C.TEST_DAYS)
    pre = rets.iloc[:pre_end]
    sigma = bl.covariance(pre.to_numpy()) if len(pre) > C.TRADING_DAYS // 12 else bl.covariance(rets.to_numpy())

    qmaps = {t: _q_lookup(stock_data, views, t) for t in tickers}

    # rebalance grid: test-period dates common to all stocks, stepped by HORIZON
    common = None
    for t in tickers:
        d = pd.DatetimeIndex(list(qmaps[t].keys()))
        common = d if common is None else common.intersection(d)
    if common is None or len(common) < 2:
        return {"ok": False, "reason": "not enough aligned test dates for a backtest"}
    grid = common.sort_values()[:: C.HORIZON]

    omega = np.asarray(views["omega"], dtype=float)
    P = np.asarray(views["P"], dtype=float)

    strat_rets, bench_rets, weight_log = [], [], []
    bench = (benchmark_close.copy() if benchmark_close is not None else None)
    if bench is not None:
        bench.index = pd.DatetimeIndex(bench.index).normalize()
        bench = bench.reindex(panel.index, method="ffill")

    for j in range(len(grid) - 1):
        t, t_next = grid[j], grid[j + 1]
        Q = np.array([qmaps[tk][t] for tk in tickers])
        res = bl.solve(sigma, w_mkt, P=P, Q=Q, omega=omega,
                       max_weight=max_weight, min_weight=min_weight)
        w = res["w_star"]
        weight_log.append((t, w))

        step = panel.loc[t_next] / panel.loc[t] - 1.0          # per-stock realised return
        strat_rets.append(float(np.dot(w, step.to_numpy())))
        if bench is not None and t in bench.index and t_next in bench.index:
            bench_rets.append(float(bench.loc[t_next] / bench.loc[t] - 1.0))

    ppy = ANN  # rebalances per year

    # ── equity curves (normalised to 1.0 at start of test window) ────────────
    start_date = grid[0]
    step_dates  = [grid[j + 1] for j in range(len(strat_rets))]
    all_dates   = pd.DatetimeIndex([start_date] + step_dates)
    strat_equity = pd.Series(
        np.concatenate([[1.0], np.cumprod(1 + np.array(strat_rets))]),
        index=all_dates,
    )

    out = {
        "ok": True,
        "n_rebalances": len(strat_rets),
        "grid_start": str(grid[0].date()),
        "grid_end": str(grid[-1].date()),
        "strategy": _metrics(np.array(strat_rets), ppy),
        "benchmark": _metrics(np.array(bench_rets), ppy) if bench_rets else None,
        "last_weights": dict(zip(tickers, weight_log[-1][1].tolist())) if weight_log else {},
        "strategy_equity": strat_equity,          # pd.Series, starts at 1.0
        "test_start_date": start_date,            # for aligning other series
    }
    return out
