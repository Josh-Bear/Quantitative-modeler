#!/usr/bin/env python3
"""
QQQ High Growth Screener — Main Entry Point
=============================================
Pipeline: build universe (rank 26-100) → run 5-point checklist → console
table → Excel workbook.

Usage:
    python3 run.py

Output:
    output/qqq_screener_output.xlsx
"""

import os, sys, time, logging
from datetime import date

SRC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
sys.path.insert(0, SRC_DIR)

from constants import (
    RANK_MIN, RANK_MAX, REV_GROWTH_THRESHOLD, GROSS_MARGIN_THRESHOLD,
    RULE_OF_40_THRESHOLD, BUY_SCORE, WATCH_SCORE,
)
from universe import build_universe
from screener import screen_universe
import excel_export

logging.basicConfig(level=logging.INFO, format="  %(levelname)s  %(message)s")
log = logging.getLogger("run")

OUTPUT_DIR  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "qqq_screener_output.xlsx")


def _mark(check) -> str:
    return {True: "✅", False: "❌"}.get(check, "➖")


def _pct(val) -> str:
    return f"{val*100:4.0f}%" if isinstance(val, (int, float)) else "  N/A"


def print_table(results: list):
    """Console table in the format from the brief."""
    print("\n" + "=" * 78)
    print(f"  QQQ HIGH GROWTH SCREENER (rank {RANK_MIN}-{RANK_MAX})")
    print(f"  Universe: {len(results)} tickers | Date: {date.today()}")
    print("=" * 78)
    print(f"{'TICKER':<7}| {'Rev Grow':>9} | {'Accel':^5} | "
          f"{'Gross Mgn':>9} | {'Rule40':>7} | {'Analyst':^7} | {'SCORE':^5} | SIGNAL")
    print("-" * 78)

    for r in results:
        if r.get("error"):
            print(f"{r['Ticker']:<7}|  fetch error: {r['error'][:40]}")
            continue
        rule40 = r.get("RuleOf40")
        rule40_s = f"{rule40:6.0f}" if isinstance(rule40, (int, float)) else "  N/A"
        print(f"{r['Ticker']:<7}| {_pct(r.get('RevGrowth'))} {_mark(r['c1'])} | "
              f"{_mark(r['c2']):^5} | {_pct(r.get('GrossMargin'))} {_mark(r['c3'])} | "
              f"{rule40_s} {_mark(r['c4'])} | {_mark(r['c5']):^7} | "
              f"{r['Score']}/5  | {r['Signal']}")

    # ── summary buckets ──
    buys   = [r["Ticker"] for r in results if r.get("Score", 0) >= BUY_SCORE]
    watch  = [r["Ticker"] for r in results
              if WATCH_SCORE <= r.get("Score", 0) < BUY_SCORE]
    print("-" * 78)
    print(f"  🟢 BUY ({BUY_SCORE}/5):   {', '.join(buys)  or '—'}")
    print(f"  🟡 WATCH ({WATCH_SCORE}/5): {', '.join(watch) or '—'}")
    print(f"  🔴 SKIP:        {len(results) - len(buys) - len(watch)} tickers")
    print("=" * 78)


def main():
    start = time.time()
    print("\n🚀 QQQ High Growth Screener\n")
    print(f"   Thresholds: rev growth >{REV_GROWTH_THRESHOLD:.0%}, "
          f"gross margin >{GROSS_MARGIN_THRESHOLD:.0%}, "
          f"Rule of 40 >{RULE_OF_40_THRESHOLD:.0f}\n")

    # 1. Universe
    universe, ranked_df, info_cache = build_universe()
    if not universe:
        log.error("Empty universe — aborting.")
        return 1

    # 2. Screen
    print(f"\n📋 Screening {len(universe)} tickers...\n")
    results, data_quality = screen_universe(universe, info_cache)

    # 3. Console output
    print_table(results)

    # 4. Excel
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    excel_export.export(results, data_quality, OUTPUT_FILE)

    elapsed = time.time() - start
    print(f"\n  ⏱  Completed in {elapsed:.0f}s")
    print(f"  📁 Output: {OUTPUT_FILE}")
    if data_quality:
        print(f"  ⚠️  {len(data_quality)} tickers had data-quality notes "
              f"(see Data Quality sheet)")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
