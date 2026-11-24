"""
experiment.py — the whole study in one call, shared by run.py and Research.ipynb.

  load market → draw out-of-sample parent orders → run every algo on them
  → summary / paired tests / breakdowns → sensitivity → in-sample check
"""
from __future__ import annotations

from . import constants as C
from . import data, orders, stats
from .engine import Arrays, Params, run


def run_experiment(sensitivity: bool = True, in_sample_check: bool = True,
                   n_base: int = C.ORDERS_PER_BUCKET, params: Params = Params()) -> dict:
    mk = data.load_market()
    ar = Arrays(mk)
    od, od_info = orders.generate(mk, n_base=n_base, period="out", horizon=params.horizon)
    res, fills = run(od, ar, params, keep_fills=True)
    res = stats.add_groups(res)
    summ = stats.summary(res)
    out = {
        "market": mk, "arrays": ar, "params": params,
        "orders": od, "orders_info": od_info, "results": res, "fills": fills,
        "summary": summ, "paired": stats.paired_tests(res), "best": stats.best_algo(summ),
        "by_hour": stats.breakdown(res, "hour"), "by_vol": stats.breakdown(res, "vol_tercile"),
    }
    if sensitivity:
        out["sensitivity"] = stats.sensitivity(od, ar, params)
    if in_sample_check:
        od_in, info_in = orders.generate(mk, n_base=n_base, period="in", horizon=params.horizon)
        res_in, _ = run(od_in, ar, params)
        out["orders_in_info"] = info_in
        out["summary_in"] = stats.summary(res_in)
    return out
