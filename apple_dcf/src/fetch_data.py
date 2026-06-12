"""
Apple DCF Model — Data Fetching Pipeline
==========================================
Each function fetches from a live source and falls back to hardcoded
constants on failure.  All monetary values in USD millions.
"""

import os, warnings, logging
from datetime import datetime, timedelta

import pandas as pd
import numpy as np

from constants import (
    TICKER, CIK, SEC_HEADERS, FALLBACK,
    HIST_INCOME, HIST_BALANCE, HIST_OTHER, HIST_SEGMENTS, HIST_YEARS,
)

log = logging.getLogger("fetch_data")
logging.basicConfig(level=logging.INFO, format="  %(levelname)s  %(message)s")

# ═══════════════════════════════════════════════════════════════
#  1. Market Data  (yfinance)
# ═══════════════════════════════════════════════════════════════

def fetch_market_data() -> dict:
    """Share price, shares outstanding, beta from Yahoo Finance."""
    try:
        import yfinance as yf
        t = yf.Ticker(TICKER)
        info = t.info
        hist = t.history(period="5d")

        price  = hist["Close"].iloc[-1] if len(hist) > 0 else info.get("regularMarketPrice")
        shares = info.get("sharesOutstanding", FALLBACK["shares_outstanding"] * 1e6)
        beta   = info.get("beta", FALLBACK["beta"])

        result = {
            "share_price":        round(price, 2),
            "shares_outstanding": round(shares / 1e6, 1),   # → millions
            "beta":               round(beta, 3),
        }
        log.info(f"Market data: price=${result['share_price']}, "
                 f"shares={result['shares_outstanding']}M, beta={result['beta']}")
        return result

    except Exception as e:
        log.warning(f"Market data fetch failed ({e}); using fallback")
        return {
            "share_price":        FALLBACK["share_price"],
            "shares_outstanding": FALLBACK["shares_outstanding"],
            "beta":               FALLBACK["beta"],
        }


# ═══════════════════════════════════════════════════════════════
#  2. Macro Data  (FRED + Damodaran)
# ═══════════════════════════════════════════════════════════════

def fetch_macro_data() -> dict:
    """Risk-free rate, expected inflation, market risk premium."""
    result = {
        "risk_free_rate":      FALLBACK["risk_free_rate"],
        "expected_inflation":  FALLBACK["expected_inflation"],
        "market_risk_premium": FALLBACK["market_risk_premium"],
    }

    # ── 10Y Treasury from FRED ──
    try:
        import requests
        url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10"
        df  = pd.read_csv(url, parse_dates=["DATE"])
        df  = df.dropna(subset=["DGS10"])
        df["DGS10"] = pd.to_numeric(df["DGS10"], errors="coerce")
        df  = df.dropna()
        latest = df.iloc[-1]["DGS10"]
        result["risk_free_rate"] = round(latest / 100, 4)
        log.info(f"10Y Treasury: {latest:.2f}%")
    except Exception as e:
        log.warning(f"FRED 10Y Treasury fetch failed ({e}); using fallback")

    # ── 10Y Breakeven Inflation from FRED ──
    try:
        import requests
        url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=T10YIE"
        df  = pd.read_csv(url, parse_dates=["DATE"])
        df["T10YIE"] = pd.to_numeric(df["T10YIE"], errors="coerce")
        df  = df.dropna()
        latest = df.iloc[-1]["T10YIE"]
        result["expected_inflation"] = round(latest / 100, 4)
        log.info(f"Expected inflation: {latest:.2f}%")
    except Exception as e:
        log.warning(f"FRED inflation fetch failed ({e}); using fallback")

    # ── Damodaran ERP ──
    try:
        import requests
        from bs4 import BeautifulSoup
        url = "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/ctryprem.html"
        resp = requests.get(url, timeout=10)
        soup = BeautifulSoup(resp.text, "lxml")
        tables = soup.find_all("table")
        for table in tables:
            for row in table.find_all("tr"):
                cells = row.find_all("td")
                if cells and "United States" in cells[0].get_text():
                    # ERP is usually in the last or second-to-last column
                    for cell in reversed(cells):
                        txt = cell.get_text().strip().replace("%", "")
                        try:
                            val = float(txt)
                            if 2 < val < 12:
                                result["market_risk_premium"] = round(val / 100, 4)
                                log.info(f"Damodaran US ERP: {val:.2f}%")
                                break
                        except ValueError:
                            continue
                    break
    except Exception as e:
        log.warning(f"Damodaran ERP fetch failed ({e}); using fallback 5.0%")

    return result


# ═══════════════════════════════════════════════════════════════
#  3. SEC EDGAR XBRL Financials
# ═══════════════════════════════════════════════════════════════

# XBRL tags for Apple's financial statements
XBRL_TAGS = {
    # Income Statement
    "total_revenue":       ["RevenueFromContractWithCustomerExcludingAssessedTax",
                            "Revenues", "SalesRevenueNet"],
    "total_cogs":          ["CostOfGoodsAndServicesSold", "CostOfRevenue"],
    "gross_profit":        ["GrossProfit"],
    "rd_expense":          ["ResearchAndDevelopmentExpense"],
    "sga_expense":         ["SellingGeneralAndAdministrativeExpense"],
    "operating_income":    ["OperatingIncomeLoss"],
    "other_income_expense":["NonoperatingIncomeExpense",
                            "OtherNonoperatingIncomeExpense"],
    "pretax_income":       ["IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
                            "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments"],
    "tax_provision":       ["IncomeTaxExpenseBenefit"],
    "net_income":          ["NetIncomeLoss"],

    # Balance Sheet
    "cash_and_equivalents":     ["CashAndCashEquivalentsAtCarryingValue"],
    "accounts_receivable":      ["AccountsReceivableNetCurrent"],
    "inventory":                ["InventoryNet"],
    "total_current_assets":     ["AssetsCurrent"],
    "ppe_net":                  ["PropertyPlantAndEquipmentNet"],
    "total_assets":             ["Assets"],
    "accounts_payable":         ["AccountsPayableCurrent"],
    "total_current_liabilities":["LiabilitiesCurrent"],
    "long_term_debt":           ["LongTermDebtNoncurrent", "LongTermDebt"],
    "total_liabilities":        ["Liabilities"],
    "stockholders_equity":      ["StockholdersEquity"],

    # Other
    "depreciation":        ["DepreciationDepletionAndAmortization",
                            "Depreciation", "DepreciationAmortizationAndAccretionNet"],
    "capex":               ["PaymentsToAcquirePropertyPlantAndEquipment"],
    "interest_expense":    ["InterestExpense", "InterestExpenseDebt"],
}


def _extract_xbrl_values(facts: dict, tag_candidates: list,
                         years: list, unit="USD") -> list:
    """
    From SEC XBRL companyfacts JSON, extract annual values for given tag.
    Returns list of values aligned with `years`.
    """
    us_gaap = facts.get("facts", {}).get("us-gaap", {})

    for tag in tag_candidates:
        tag_data = us_gaap.get(tag, {})
        entries  = tag_data.get("units", {}).get(unit, [])
        if not entries:
            continue

        # Filter to 10-K annual filings
        annual = [e for e in entries
                  if e.get("form") == "10-K" and e.get("fp") == "FY"]

        if not annual:
            continue

        # Build {fiscal_year: value} map
        by_fy = {}
        for e in annual:
            fy  = e.get("fy")
            val = e.get("val")
            if fy and val is not None:
                by_fy[fy] = val / 1e6  # convert to millions

        # Align to requested years
        result = [by_fy.get(yr) for yr in years]
        if any(v is not None for v in result):
            return result

    return [None] * len(years)


def fetch_sec_financials(cik: str = CIK) -> dict:
    """
    Fetch 5 years of financials from SEC EDGAR XBRL API.
    Falls back to hardcoded HIST_INCOME / HIST_BALANCE / HIST_OTHER.
    """
    try:
        import requests
        url  = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
        resp = requests.get(url, headers=SEC_HEADERS, timeout=15)
        resp.raise_for_status()
        facts = resp.json()
        log.info("SEC EDGAR XBRL data fetched successfully")

        result = {}
        for key, tags in XBRL_TAGS.items():
            unit = "USD"
            vals = _extract_xbrl_values(facts, tags, HIST_YEARS, unit)

            # Check completeness — fall back to hardcoded if too many gaps
            non_null = [v for v in vals if v is not None]
            if len(non_null) >= 3:
                result[key] = vals
            else:
                # Use hardcoded fallback for this line item
                fallback_src = {**HIST_INCOME, **HIST_BALANCE, **HIST_OTHER}
                if key in fallback_src:
                    result[key] = fallback_src[key]
                    log.warning(f"  {key}: SEC data incomplete, using fallback")
                else:
                    result[key] = vals

        return result

    except Exception as e:
        log.warning(f"SEC EDGAR fetch failed ({e}); using full fallback data")
        return {**HIST_INCOME, **HIST_BALANCE, **HIST_OTHER}


# ═══════════════════════════════════════════════════════════════
#  4. Segment Revenue
# ═══════════════════════════════════════════════════════════════

def fetch_segment_revenue() -> dict:
    """
    5-year segment revenue.
    Primary: FMP API (if FMP_API_KEY env var set).
    Fallback: hardcoded from Apple 10-K filings.
    """
    api_key = os.environ.get("FMP_API_KEY", "")

    if api_key:
        try:
            import requests
            url = (f"https://financialmodelingprep.com/api/v4/"
                   f"revenue-product-segmentation?symbol={TICKER}&apikey={api_key}")
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            log.info(f"FMP segment data: {len(data)} records")
            # Parse FMP response into our format
            # (structure varies; use fallback if parsing fails)
            return _parse_fmp_segments(data)
        except Exception as e:
            log.warning(f"FMP segment fetch failed ({e}); using fallback")

    log.info("Using hardcoded segment revenue (from Apple 10-K filings)")
    return dict(HIST_SEGMENTS)


def _parse_fmp_segments(data: list) -> dict:
    """Parse FMP segment data into {segment: [values by year]}."""
    # FMP returns list of dicts with year and segment revenues
    segments = {k: [] for k in HIST_SEGMENTS.keys()}
    for entry in sorted(data, key=lambda x: list(x.keys())[0] if x else ""):
        for date_key, seg_data in entry.items():
            if not isinstance(seg_data, dict):
                continue
            for seg_name, val in seg_data.items():
                # Map FMP segment names to our names
                mapped = _map_fmp_segment(seg_name)
                if mapped and mapped in segments:
                    segments[mapped].append(val / 1e6 if val > 1e9 else val)
    # Validate — if incomplete, fall back
    for k, v in segments.items():
        if len(v) < 3:
            return dict(HIST_SEGMENTS)
    return segments


def _map_fmp_segment(name: str) -> str:
    name_lower = name.lower()
    if "iphone" in name_lower:     return "iPhone"
    if "mac" in name_lower:        return "Mac"
    if "ipad" in name_lower:       return "iPad"
    if "wearable" in name_lower:   return "Wearables"
    if "service" in name_lower:    return "Services"
    return ""


# ═══════════════════════════════════════════════════════════════
#  5. Derived Assumptions
# ═══════════════════════════════════════════════════════════════

def compute_derived_assumptions(financials: dict, market: dict) -> dict:
    """
    Compute: effective tax rate, cost of debt, Products/Services GP%,
    D&A%, CapEx%, working capital metrics (DSO/DIO/DPO).
    """
    result = {}

    # ── Effective Tax Rate (3yr avg) ──
    pretax = financials.get("pretax_income", HIST_INCOME["pretax_income"])
    tax    = financials.get("tax_provision", HIST_INCOME["tax_provision"])
    rates  = []
    for i in range(max(0, len(pretax) - 3), len(pretax)):
        if pretax[i] and tax[i] and pretax[i] > 0:
            rates.append(tax[i] / pretax[i])
    result["effective_tax_rate"] = round(np.mean(rates), 4) if rates else FALLBACK["effective_tax_rate"]
    log.info(f"Effective tax rate: {result['effective_tax_rate']:.1%}")

    # ── Cost of Debt (implied: interest expense / avg total debt) ──
    interest = financials.get("interest_expense", HIST_OTHER["interest_expense"])
    lt_debt  = financials.get("long_term_debt", HIST_BALANCE["long_term_debt"])
    st_debt  = HIST_BALANCE.get("short_term_debt", [0]*5)
    total_debt = [lt + st for lt, st in zip(lt_debt, st_debt)]
    rates = []
    for i in range(1, len(interest)):
        avg_debt = (total_debt[i] + total_debt[i-1]) / 2
        if avg_debt > 0 and interest[i]:
            rates.append(interest[i] / avg_debt)
    result["cost_of_debt"] = round(np.mean(rates), 4) if rates else FALLBACK["cost_of_debt"]
    log.info(f"Implied cost of debt: {result['cost_of_debt']:.2%}")

    # ── Products / Services GP% ──
    prod_rev  = financials.get("products_revenue", HIST_INCOME["products_revenue"])
    serv_rev  = financials.get("services_revenue", HIST_INCOME["services_revenue"])
    prod_cogs = financials.get("products_cogs", HIST_INCOME["products_cogs"])
    serv_cogs = financials.get("services_cogs", HIST_INCOME["services_cogs"])

    result["products_gp_pct"] = []
    result["services_gp_pct"] = []
    for i in range(len(prod_rev)):
        pr = prod_rev[i] if prod_rev[i] else 1
        sr = serv_rev[i] if serv_rev[i] else 1
        pc = prod_cogs[i] if prod_cogs[i] else 0
        sc = serv_cogs[i] if serv_cogs[i] else 0
        result["products_gp_pct"].append(round(1 - pc / pr, 4))
        result["services_gp_pct"].append(round(1 - sc / sr, 4))
    log.info(f"Products GP%: {[f'{x:.1%}' for x in result['products_gp_pct']]}")
    log.info(f"Services GP%: {[f'{x:.1%}' for x in result['services_gp_pct']]}")

    # ── D&A and CapEx as % of revenue ──
    revenue = financials.get("total_revenue", HIST_INCOME["total_revenue"])
    da      = financials.get("depreciation", HIST_OTHER["depreciation"])
    capex   = financials.get("capex", HIST_OTHER["capex"])
    result["da_pct_rev"]    = [round(d / r, 4) if r else 0 for d, r in zip(da, revenue)]
    result["capex_pct_rev"] = [round(c / r, 4) if r else 0 for c, r in zip(capex, revenue)]

    # ── Working Capital: DSO, DIO, DPO ──
    ar  = financials.get("accounts_receivable", HIST_BALANCE["accounts_receivable"])
    inv = financials.get("inventory", HIST_BALANCE["inventory"])
    ap  = financials.get("accounts_payable", HIST_BALANCE["accounts_payable"])
    cogs = financials.get("total_cogs", HIST_INCOME["total_cogs"])

    result["dso"] = [round(a / (r / 365), 1) if r else 0 for a, r in zip(ar, revenue)]
    result["dio"] = [round(i / (c / 365), 1) if c else 0 for i, c in zip(inv, cogs)]
    result["dpo"] = [round(p / (c / 365), 1) if c else 0 for p, c in zip(ap, cogs)]
    log.info(f"DSO: {result['dso']}, DIO: {result['dio']}, DPO: {result['dpo']}")

    return result


# ═══════════════════════════════════════════════════════════════
#  Master Fetch  (called by run.py)
# ═══════════════════════════════════════════════════════════════

def fetch_all() -> dict:
    """Run the entire data pipeline. Returns a unified data dict."""
    log.info("=" * 50)
    log.info("  Starting data fetch pipeline")
    log.info("=" * 50)

    market     = fetch_market_data()
    macro      = fetch_macro_data()
    financials = fetch_sec_financials()
    segments   = fetch_segment_revenue()
    derived    = compute_derived_assumptions(financials, market)

    # Merge into one dict
    data = {
        "market":     market,
        "macro":      macro,
        "financials": financials,
        "segments":   segments,
        "derived":    derived,
    }

    log.info("=" * 50)
    log.info("  Data fetch complete")
    log.info("=" * 50)
    return data


# ─── standalone test ────────────────────────────────────────────
if __name__ == "__main__":
    import json
    data = fetch_all()
    print("\n=== MARKET ===")
    print(json.dumps(data["market"], indent=2))
    print("\n=== MACRO ===")
    print(json.dumps(data["macro"], indent=2))
    print("\n=== DERIVED ===")
    print(json.dumps(data["derived"], indent=2, default=str))
    print("\n=== SEGMENTS ===")
    for seg, vals in data["segments"].items():
        print(f"  {seg}: {vals}")
