"""
run.py — execution-algorithm research, end to end, without the notebook.

    python run.py              # full study (~30 s): main run + sensitivity
    python run.py --quick      # 200 base draws, no sensitivity (smoke test)

Writes output/*.csv and output/report.txt. Research.ipynb runs the same
experiment (src/experiment.py) and adds the charts.
"""
from __future__ import annotations

import argparse

import pandas as pd

from src import constants as C
from src.experiment import run_experiment

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 30)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--quick", action="store_true")
    args = ap.parse_args()
    n = 200 if args.quick else C.ORDERS_PER_BUCKET
    ex = run_experiment(sensitivity=not args.quick, n_base=n)

    lines = []
    emit = lambda s="": (print(s), lines.append(str(s)))
    mk, info = ex["market"], ex["orders_info"]
    emit("=" * 78)
    emit("EXECUTION ALGORITHM RESEARCH — SET50 hourly, " + " vs ".join(C.ALGOS))
    emit("=" * 78)
    emit(f"data     : {', '.join(mk.info['files'])}  ({mk.info['start']} → {mk.info['end']})")
    emit(f"universe : {', '.join(C.TICKERS)} (locked); VWAP profile = rolling {C.PROFILE_DAYS}-day, "
         f"first {mk.info['first_profile_day']}")
    emit(f"orders   : {info['n_orders']:,} = {info['n_base']:,} draws × {len(C.SIZE_BUCKETS_PCT_NAV)} sizes "
         f"(NAV {C.NAV_THB / 1e6:,.0f}M), decisions {info['first_decision_allowed']} → "
         f"{info['last_decision_allowed']}, rejected draws {info['rejected_draws']}")
    emit(f"params   : {ex['params']}")
    emit()
    cols = ["bucket", "algo", "pct_adv_mean", "is_mean", "is_ci_lo", "is_ci_hi", "is_std", "timing_mean",
            "spread_mean", "impact_mean", "commission_mean", "opportunity_mean", "vs_ivwap_mean",
            "fully_filled_share"]
    s = ex["summary"][cols].copy()
    s["pct_adv_mean"] *= 100
    emit("Implementation shortfall (bps; pct_adv in %)")
    emit(s.round(2).to_string(index=False))
    emit()
    emit("Paired differences a − b (bps, < 0 → a cheaper), Holm-adjusted within bucket")
    p = ex["paired"][["bucket", "a", "b", "mean_diff", "ci_lo", "ci_hi", "share_a_cheaper", "t_p_holm",
                      "wilcoxon_p", "significant"]]
    emit(p.round(4).to_string(index=False))
    emit()
    emit("Cheapest algo per size")
    emit(ex["best"].round(3).to_string(index=False))
    if "sensitivity" in ex:
        emit()
        emit("Sensitivity — cheapest algo per bucket for each parameter value")
        sens = ex["sensitivity"]
        win = sens[sens["rank"] == 1].pivot_table(index=["param", "value"], columns="bucket",
                                                  values="algo", aggfunc="first")
        emit(win[sorted(win.columns, key=lambda b: float(b.split('%')[0]))].to_string())
    emit()
    emit("Mean IS by year (bps)")
    emit(ex["by_year"].round(2).to_string(index=False))

    C.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for name in ["orders", "results", "fills", "summary", "paired", "by_hour", "by_vol", "by_year",
                 "sensitivity"]:
        if name in ex:
            ex[name].to_csv(C.OUTPUT_DIR / f"{name}.csv", index=False)
    (C.OUTPUT_DIR / "report.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n→ {C.OUTPUT_DIR}/ (report.txt + csv)")


if __name__ == "__main__":
    main()
