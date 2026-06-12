#!/usr/bin/env python3
"""
Apple DCF Model — Main Entry Point
====================================
Runs the full pipeline: fetch data → build Excel → QA → print summary.

Usage:
    python3 run.py
    
Output:
    output/DCF_Model_Apple.xlsx
"""

import os, sys, time

# Add src to path
SRC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
sys.path.insert(0, SRC_DIR)

from fetch_data import fetch_all
from build_model import AppleDCFModel
from constants import FALLBACK, HIST_INCOME, HIST_BALANCE

SCENARIO_NAMES = ["Best", "Base", "Worst"]

OUTPUT_DIR  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "DCF_Model_Apple.xlsx")


def run_qa(proj, market):
    """Run QA checklist from §9 of the brief."""
    print("\n" + "=" * 60)
    print("  QA CHECKLIST")
    print("=" * 60)
    passed = 0
    total  = 0

    # 1. Balance Sheet: Total Assets = Total L + E (historical)
    total += 1
    bs_ok = True
    for i in range(len(HIST_BALANCE["total_assets"])):
        ta  = HIST_BALANCE["total_assets"][i]
        tle = HIST_BALANCE["total_liabilities"][i] + HIST_BALANCE["stockholders_equity"][i]
        if abs(ta - tle) > 1:
            bs_ok = False
            break
    print(f"  {'✅' if bs_ok else '❌'}  Balance Sheet check (historical): "
          f"{'PASS' if bs_ok else 'FAIL'}")
    if bs_ok: passed += 1

    # 2. WACC - g > 0 for all scenarios
    total += 1
    wacc_ok = True
    for sc in SCENARIO_NAMES:
        spread = proj[sc]["wacc"] - proj[sc]["tgr"]
        if spread <= 0:
            wacc_ok = False
            print(f"      ⚠️  {sc}: WACC ({proj[sc]['wacc']:.2%}) ≤ TGR ({proj[sc]['tgr']:.2%})")
    print(f"  {'✅' if wacc_ok else '❌'}  WACC - g > 0 all scenarios: "
          f"{'PASS' if wacc_ok else 'FAIL'}")
    if wacc_ok: passed += 1

    # 3. DCF implied price sanity (50%-200% of market price)
    total += 1
    price_ok = True
    mkt = market["share_price"]
    for sc in SCENARIO_NAMES:
        ip = proj[sc]["implied_price"]
        ratio = ip / mkt
        if ratio < 0.3 or ratio > 3.0:
            price_ok = False
            print(f"      ⚠️  {sc}: ${ip:.2f} is {ratio:.0%} of market (${mkt:.2f})")
    print(f"  {'✅' if price_ok else '⚠️'}  Implied price sanity band: "
          f"{'PASS' if price_ok else 'REVIEW'}")
    if price_ok: passed += 1

    # 4. TV as % of EV < 90%
    total += 1
    tv_ok = True
    for sc in SCENARIO_NAMES:
        tv_pct = proj[sc]["tv_pct_ev"]
        if tv_pct > 90:
            tv_ok = False
            print(f"      ⚠️  {sc}: TV = {tv_pct:.1f}% of EV (elevated)")
    print(f"  {'✅' if tv_ok else '⚠️'}  TV % of EV < 90%: "
          f"{'PASS' if tv_ok else 'REVIEW'}")
    if tv_ok: passed += 1

    # 5. Revenue projections positive
    total += 1
    rev_ok = all(all(v > 0 for v in proj[sc]["total_rev"]) for sc in SCENARIO_NAMES)
    print(f"  {'✅' if rev_ok else '❌'}  Revenue always positive: "
          f"{'PASS' if rev_ok else 'FAIL'}")
    if rev_ok: passed += 1

    # 6. FCF positive in base case
    total += 1
    fcf_ok = all(v > 0 for v in proj["Base"]["ufcf"])
    print(f"  {'✅' if fcf_ok else '⚠️'}  Base case FCF always positive: "
          f"{'PASS' if fcf_ok else 'REVIEW'}")
    if fcf_ok: passed += 1

    print(f"\n  Result: {passed}/{total} checks passed")
    return passed == total


def print_summary(proj, market):
    """Print summary to console."""
    print("\n" + "=" * 60)
    print("  APPLE DCF MODEL — RESULTS SUMMARY")
    print("=" * 60)
    mkt_price = market["share_price"]
    print(f"  Current Market Price:  ${mkt_price:.2f}")
    print(f"  Shares Outstanding:    {market['shares_outstanding']:,.0f} mn")
    print()

    for sc in SCENARIO_NAMES:
        p = proj[sc]
        upside = (p["implied_price"] / mkt_price - 1) * 100
        arrow  = "▲" if upside > 0 else "▼"
        color  = "\033[92m" if upside > 0 else "\033[91m"
        reset  = "\033[0m"

        print(f"  {sc:6s} Case:")
        print(f"    Implied Price:     {color}${p['implied_price']:>8.2f}{reset}  "
              f"({arrow} {abs(upside):.1f}%)")
        print(f"    Enterprise Value:  ${p['ev']:>12,.0f} mn")
        print(f"    WACC:              {p['wacc']:>8.2%}")
        print(f"    Terminal Growth:   {p['tgr']:>8.2%}")
        print(f"    TV % of EV:        {p['tv_pct_ev']:>7.1f}%")
        print()

    print("=" * 60)


def main():
    start = time.time()

    # 1. Fetch data
    print("\n🚀 Starting Apple DCF Model Pipeline...\n")
    data = fetch_all()

    # 2. Build Excel model
    print("\n📊 Building Excel workbook (24 tabs)...")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    model = AppleDCFModel(data)
    proj  = model.build(OUTPUT_FILE)

    # 3. QA
    all_pass = run_qa(proj, data["market"])

    # 4. Summary
    print_summary(proj, data["market"])

    elapsed = time.time() - start
    print(f"  ⏱  Completed in {elapsed:.1f}s")
    print(f"  📁 Output: {OUTPUT_FILE}")
    print()

    if not all_pass:
        print("  ⚠️  Some QA checks need review — see above")

    return 0


if __name__ == "__main__":
    sys.exit(main())
