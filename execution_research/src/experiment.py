"""
experiment.py — the whole study in one call, shared by run.py and Research.ipynb.

  load market → draw parent orders over the whole backtest → run every algo on them
  → summary / paired tests / breakdowns (hour, volatility, year) → sensitivity
"""
from __future__ import annotations

from . import constants as C
from . import data, orders, stats
from .engine import Arrays, Params, run


def run_experiment(sensitivity: bool = True, n_base: int = C.ORDERS_PER_BUCKET,
                   params: Params = Params()) -> dict:
    mk = data.load_market()
    ar = Arrays(mk)
    od, od_info = orders.generate(mk, n_base=n_base, horizon=params.horizon)
    res, fills = run(od, ar, params, keep_fills=True)
    res = stats.add_groups(res)
    summ = stats.summary(res)
    out = {
        "market": mk, "arrays": ar, "params": params,
        "orders": od, "orders_info": od_info, "results": res, "fills": fills,
        "summary": summ, "paired": stats.paired_tests(res), "best": stats.best_algo(summ),
        "by_hour": stats.breakdown(res, "hour"), "by_vol": stats.breakdown(res, "vol_tercile"),
        "by_year": stats.breakdown(res, "year"),
    }
    if sensitivity:
        out["sensitivity"] = stats.sensitivity(od, ar, params)
    return out
