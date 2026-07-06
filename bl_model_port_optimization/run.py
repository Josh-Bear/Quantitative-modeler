"""
run.py — orchestrate the ML-driven Black-Litterman portfolio pipeline end to end.

  M1 data → M2 features → (SVR tune once) → M7 walk-forward backtest
  (which runs M3 predict → M4 select → M5 BL → M6 optimise per rebalance) → M8 report.

Profiles (07 §5 — dev convenience, not a change to the locked design):
    python run.py --quick     # 22 stocks, 2 rebalances, 5 epochs  (smoke test)
    python run.py             # ~44 stocks, 4 rebalances, 30 epochs (default)
    python run.py --full      # live S&P 100 (see 09_OPEN_DECISIONS.md §11), full
                               # quarterly schedule, 100 epochs (slow, still hours)
    python run.py --jobs 8    # fan out per-stock training across 8 CPU workers
    python test.py            # network-free core sanity checks
"""
from __future__ import annotations

import argparse
import sys
import warnings

from src import constants as C
from src import data_pipeline as dp
from src import features as ft
from src import ml_model as ml
from src import backtest as bt
from src import evaluation as ev


def parse_args():
    p = argparse.ArgumentParser(description="ML-driven Black-Litterman portfolio backtest")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--quick", action="store_true", help="smoke profile")
    g.add_argument("--full", action="store_true", help="full S&P 500 paper scope")
    p.add_argument("--jobs", type=int, default=1, help="CPU workers for per-stock training")
    p.add_argument("--epochs", type=int, default=None,
                   help="override the profile's LSTM epochs (e.g. --full --epochs 40 for a "
                        "faster full run)")
    p.add_argument("--device", default="cpu", choices=["cpu", "mps", "cuda"])
    p.add_argument("--force-data", action="store_true", help="re-download / recompute data")
    return p.parse_args()


def main() -> int:
    # line-buffer stdout so progress is visible when piped to a file (long backtests)
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:  # noqa: BLE001
        pass
    args = parse_args()
    profile = "quick" if args.quick else "full" if args.full else "default"
    cfg = C.resolve_profile(profile)
    if args.epochs is not None:          # CLI override of the profile's epochs
        cfg["epochs"] = args.epochs
    device = ml.get_device(args.device)
    print(f"=== BL portfolio pipeline | profile={profile} | epochs={cfg['epochs']} "
          f"| jobs={args.jobs} | device={device} ===")

    # ---- M1: data ----
    print("\n[1/5] Data pipeline …")
    info = dp.run_data_pipeline(universe=cfg["universe"], force=args.force_data)
    tickers, sector_map = info["tickers"], info["sector_map"]
    if len(tickers) < 2:
        print("FATAL: <2 tickers with data — aborting."); return 1

    # ---- M2: features ----
    print("\n[2/5] Feature engineering …")
    tickers = ft.run_feature_engineering(tickers, force=args.force_data)
    sector_map = {t: s for t, s in sector_map.items() if t in tickers}

    # ---- rebalance schedule + SVR tuning (once, 09 §4) ----
    calendar = bt.trading_calendar(tickers)
    reb_dates = bt.generate_rebalance_dates(C.BACKTEST_START, C.BACKTEST_END, calendar)
    if cfg["max_rebalances"]:
        reb_dates = reb_dates[:cfg["max_rebalances"]]
    if not reb_dates:
        print("FATAL: no rebalance dates in window — aborting."); return 1

    print("\n[3/5] SVR hyperparameter tuning …")
    if cfg["tune_svr"]:
        sample = tickers[:C.SVR_TUNE_SAMPLE]
        svr_C, svr_eps = ml.tune_svr_hyperparams(sample, reb_dates[0],
                                                 epochs=cfg["epochs"], device=device)
    else:
        svr_C, svr_eps = C.SVR_C, C.SVR_EPSILON
        print(f"[3/5] tuning skipped — placeholder C={svr_C}, epsilon={svr_eps}.")

    # ---- M7: walk-forward backtest (runs M3-M6 per date) ----
    print("\n[4/5] Walk-forward backtest …")
    rf_annual = bt.get_risk_free_rate()
    results = bt.run_backtest(tickers, sector_map, epochs=cfg["epochs"],
                              svr_C=svr_C, svr_eps=svr_eps, n_jobs=args.jobs,
                              max_rebalances=cfg["max_rebalances"], rf_annual=rf_annual)
    if results.empty:
        print("FATAL: backtest produced no periods — aborting."); return 1

    # ---- M8: evaluation + report (markdown + PDF) ----
    print("\n[5/5] Evaluation & report …")
    ev.generate_report(results, sector_map, reb_dates, rf_annual=rf_annual)
    try:
        from src import report_pdf
        report_pdf.build_pdf_report()
    except Exception as e:  # noqa: BLE001 — PDF is a bonus, never fail the run for it
        warnings.warn(f"[M8] PDF report skipped: {e}")

    _summary(results, rf_annual)
    _qa(results)
    return 0


def _summary(results, rf_annual: float) -> None:
    r = results.set_index("date")["period_return"]
    pv = results.set_index("date")["portfolio_value"]
    print("\n──────── SUMMARY ────────")
    print(f"  rebalances counted : {len(results)}")
    print(f"  final value (×)    : {pv.iloc[-1]:.3f}")
    print(f"  annualised return  : {ev.annualized_return(r):.2%}")
    print(f"  annualised vol     : {ev.annualized_volatility(r):.2%}")
    print(f"  Sharpe (rf={rf_annual:.2%}) : {ev.sharpe_ratio(r, rf_annual):.3f}")
    print(f"  max drawdown       : {ev.max_drawdown(pv):.2%}")
    print(f"  total tx cost      : {results['transaction_cost'].sum():.2%}")


def _qa(results) -> None:
    """Lightweight QA checklist (mirrors the other models' run.py)."""
    print("\n──────── QA ────────")
    checks = {
        "≥1 rebalance period recorded": len(results) >= 1,
        "no NaN period returns": not results["period_return"].isna().any(),
        "portfolio value positive": (results["portfolio_value"] > 0).all(),
        "transaction costs in [0, 1]": results["transaction_cost"].between(0, 1).all(),
    }
    for name, ok in checks.items():
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    if not all(checks.values()):
        warnings.warn("[QA] one or more checks failed — inspect results.")


if __name__ == "__main__":
    sys.exit(main())
