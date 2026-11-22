"""
run.py — order-execution simulator, end to end.

    load hourly bars → signals → pre-trade → execute (MARKET vs TWAP) → metrics → Excel + report

Usage:
    python run.py                       # reads every SET50_*.csv next to this file
    python run.py --csv a.csv b.csv     # explicit file(s), long format
    python run.py --synthetic           # GBM prices, runs without any data file

Outputs: output/order_execution.xlsx and output/report.txt
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from src import constants as C
from src import data_loader, metrics, signals, simulator
from src.excel_export import COMPARISON_LABELS, write_workbook

_LINES: list[str] = []


def emit(line: str = "") -> None:
    print(line)
    _LINES.append(line)


def parse_args():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", type=Path, nargs="+", default=None,
                    help=f"long-format hourly file(s); default: {C.DATA_GLOB} in this folder")
    ap.add_argument("--synthetic", action="store_true", help="use GBM prices instead of a CSV")
    return ap.parse_args()


def load(args) -> data_loader.MarketData:
    if args.synthetic:
        return data_loader.synthetic_prices()
    paths = args.csv or data_loader.data_files()
    missing = [p for p in paths if not Path(p).exists()]
    if not paths or missing:
        sys.exit(f"data not found: {missing or C.DATA_GLOB}\n"
                 f"→ put {C.DATA_GLOB} in {C.ROOT}, pass --csv, or run with --synthetic")
    return data_loader.load_csv(paths)


def combined_nav(results: dict[str, dict]) -> pd.DataFrame:
    parts = []
    for name, res in results.items():
        nav = res["nav"]
        keep = ["nav", "cash"] + [c for c in nav.columns if c.startswith("w_")]
        parts.append(nav[keep].add_suffix(f"_{name}"))
    return pd.concat(parts, axis=1).reset_index()


def main():
    args = parse_args()
    md = load(args)
    prices, info = md.close, md.info
    emit("=" * 72)
    emit("ORDER EXECUTION SIMULATOR — SET hourly bars")
    emit("=" * 72)
    emit(f"data      : {', '.join(info['files'])}")
    emit(f"tickers   : {', '.join(prices.columns)}")
    emit(f"bars      : {len(prices):,}  ({info['start']} → {info['end']}, "
         f"{data_loader.bars_per_day(prices.index)} bars/day)")
    if info.get("warning"):
        emit(f"WARNING   : {info['warning']}")
    if info.get("rows_off_grid_dropped"):
        emit(f"dropped   : {info['rows_off_grid_dropped']:,} rows outside bar hours {C.SESSION_HOURS}")
    gaps = {k: v for k, v in info["missing_bars"].items() if v}
    if gaps:
        emit(f"no-trade  : {gaps}  (close ffilled, value = 0 → no fill in that bar)")

    sig = signals.compute_all(prices)
    sig_events = signals.signals_long(sig, only_events=True)
    counts = sig_events["signal"].value_counts().to_dict()
    emit(f"signals   : BUY {counts.get('BUY', 0)}  SELL {counts.get('SELL', 0)}")

    results = simulator.run_all(md, sig)
    orders, comp = metrics.comparison(results, md)
    fills = pd.concat([pd.DataFrame(r["fills"]) for r in results.values()], ignore_index=True)
    log = pd.concat([pd.DataFrame(r["pretrade_log"]) for r in results.values()], ignore_index=True)

    emit()
    emit(f"{'metric':<44}" + "".join(f"{n:>14}" for n in comp.columns))
    emit("-" * (44 + 14 * comp.shape[1]))
    for key, (label, fmt) in COMPARISON_LABELS.items():
        if key not in comp.index:
            continue
        cells = []
        for v in comp.loc[key]:
            if "%" in fmt:
                cells.append(f"{v:>14.2%}")
            elif fmt == "#,##0":
                cells.append(f"{v:>14,.0f}")
            elif fmt == "0":
                cells.append(f"{int(v):>14d}")
            else:
                cells.append(f"{v:>14.2f}")
        emit(f"{label:<44}" + "".join(cells))

    if len(log):
        emit()
        emit("pre-trade log (count by check / action):")
        tbl = log.groupby(["strategy", "check", "action"]).size().rename("n").reset_index()
        for _, r in tbl.iterrows():
            emit(f"  {r['strategy']:<8} {r['check']:<14} {r['action']:<7} {r['n']:>6}")

    path = write_workbook(C.EXCEL_PATH, sig_events, log, orders, fills, comp,
                          combined_nav(results), info)
    emit()
    emit(f"Excel     → {path}")
    C.REPORT_PATH.write_text("\n".join(_LINES) + "\n", encoding="utf-8")
    print(f"report    → {C.REPORT_PATH}")


if __name__ == "__main__":
    main()
