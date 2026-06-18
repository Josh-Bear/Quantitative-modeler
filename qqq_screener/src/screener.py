"""
QQQ High Growth Screener — Checklist Engine
=============================================
Runs the 5-point high-growth checklist against a single ticker.

Each check returns True (pass), False (fail), or None (N/A — data missing,
not counted toward the score). The score is the number of True checks.

Checks
------
1. Revenue growth      revenueGrowth > REV_GROWTH_THRESHOLD
2. Revenue accelerating latest-quarter YoY growth > prior-quarter YoY growth
3. Gross margin        grossMargins > GROSS_MARGIN_THRESHOLD AND expanding YoY
4. Rule of 40          revGrowth% + FCF margin% > RULE_OF_40_THRESHOLD
5. Analyst revise up   forwardEps > trailingEps
"""

import time
import logging

import pandas as pd

from constants import (
    REV_GROWTH_THRESHOLD, GROSS_MARGIN_THRESHOLD, RULE_OF_40_THRESHOLD,
    BUY_SCORE, WATCH_SCORE, RATE_LIMIT_SLEEP,
)

log = logging.getLogger("screener")


def _num(v):
    """Return v as a usable number, or None for missing/NaN values."""
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        return None
    return v


def _row(df, *names):
    """Return the first matching row of a yfinance statement DataFrame, or None."""
    if df is None or getattr(df, "empty", True):
        return None
    for n in names:
        if n in df.index:
            vals = [_num(v) for v in df.loc[n].tolist()]
            if any(v is not None for v in vals):
                return vals
    return None


def _signal(score: int) -> str:
    if score >= BUY_SCORE:
        return "🟢"
    if score >= WATCH_SCORE:
        return "🟡"
    return "🔴"


def screen_ticker(ticker: str, info: dict = None) -> dict:
    """
    Run the checklist on one ticker. `info` may be a pre-fetched .info dict
    (from the ranking pass) to avoid a redundant network call.
    """
    import yfinance as yf

    notes = []          # data-quality / edge-case flags
    t = yf.Ticker(ticker)

    if info is None:
        try:
            info = t.info
        except Exception as e:
            return {
                "Ticker": ticker, "error": f"info fetch failed: {e}",
                "Score": 0, "Signal": "🔴", "notes": ["fetch failed"],
            }

    # ── Raw inputs ──────────────────────────────────────────────
    rev_growth   = info.get("revenueGrowth")
    gross_margin = info.get("grossMargins")
    total_rev    = info.get("totalRevenue")
    fwd_eps      = info.get("forwardEps")
    trail_eps    = info.get("trailingEps")

    # ── Check 1: Revenue growth ─────────────────────────────────
    if rev_growth is None:
        c1 = None
        notes.append("revenueGrowth N/A")
    else:
        c1 = rev_growth > REV_GROWTH_THRESHOLD

    # ── Check 2: Revenue accelerating ───────────────────────────
    # latest-quarter YoY growth vs most-recent full-year YoY growth.
    # Quarterly columns are irregularly spaced, so the year-ago quarter
    # is matched by date (within ~45 days) rather than by position.
    accel = None
    try:
        qdf  = t.quarterly_income_stmt
        arev = _row(t.income_stmt, "Total Revenue", "TotalRevenue")
        qser = None
        for name in ("Total Revenue", "TotalRevenue"):
            if qdf is not None and not qdf.empty and name in qdf.index:
                qser = qdf.loc[name].dropna()
                break

        if (qser is not None and len(qser) >= 5
                and arev and len(arev) >= 2 and arev[0] and arev[1]):
            dates  = list(qser.index)
            target = dates[0] - pd.DateOffset(years=1)
            yago   = min(range(len(dates)),
                         key=lambda i: abs((dates[i] - target).days))
            if abs((dates[yago] - target).days) <= 45 and qser.iloc[yago]:
                q_yoy  = qser.iloc[0] / qser.iloc[yago] - 1
                fy_yoy = arev[0] / arev[1] - 1
                accel  = q_yoy > fy_yoy
            else:
                notes.append("acceleration N/A (no clean year-ago quarter)")
        else:
            notes.append("acceleration N/A (insufficient data)")
    except Exception:
        notes.append("acceleration N/A (quarterly fetch failed)")
    c2 = accel

    # ── Check 3: Gross margin high AND expanding ────────────────
    c3 = None
    gm_latest = gm_prior = None
    try:
        inc = t.income_stmt
        gp  = _row(inc, "Gross Profit")
        rev = _row(inc, "Total Revenue", "TotalRevenue")
        if gp and rev and len(gp) >= 2 and rev[0] and rev[1]:
            gm_latest = gp[0] / rev[0]
            gm_prior  = gp[1] / rev[1]
    except Exception:
        pass

    if gross_margin is None and gm_latest is None:
        notes.append("grossMargins N/A")
    else:
        current_gm = gross_margin if gross_margin is not None else gm_latest
        high = current_gm > GROSS_MARGIN_THRESHOLD
        if gm_latest is not None and gm_prior is not None:
            c3 = high and (gm_latest > gm_prior)
        else:
            # can't confirm expansion → pass only the level test, flag it
            c3 = high if not high else None
            notes.append("GM expansion N/A (only level checked)")

    # ── Check 4: Rule of 40 ─────────────────────────────────────
    rule40 = None
    fcf = None
    try:
        cf    = t.cashflow
        ocf   = _row(cf, "Operating Cash Flow", "OperatingCashFlow")
        capex = _row(cf, "Capital Expenditure", "CapitalExpenditure")
        if ocf and capex and ocf[0] is not None and capex[0] is not None:
            fcf = ocf[0] + capex[0]          # capex is reported negative
    except Exception:
        pass
    if fcf is None:
        fcf = _num(info.get("freeCashflow"))

    if rev_growth is not None and fcf is not None and total_rev:
        fcf_margin = fcf / total_rev * 100
        rule40 = rev_growth * 100 + fcf_margin
        c4 = rule40 > RULE_OF_40_THRESHOLD
        if fcf < 0:
            notes.append("negative FCF")
    else:
        c4 = None
        notes.append("Rule of 40 N/A")

    # ── Check 5: Analyst revise up (forward vs trailing EPS) ────
    if fwd_eps is None or trail_eps is None:
        c5 = None
        notes.append("EPS revise N/A")
    else:
        c5 = fwd_eps > trail_eps

    # Normalize to Python bool/None: pandas comparisons (e.g. Check 2) yield
    # numpy.bool_, and `np.True_ is True` is False — an identity check would
    # silently drop those passes from the score.
    checks = [None if c is None else bool(c) for c in (c1, c2, c3, c4, c5)]
    c1, c2, c3, c4, c5 = checks
    score = sum(1 for c in checks if c is True)

    return {
        "Ticker":        ticker,
        "RevGrowth":     rev_growth,
        "Accelerating":  c2,
        "GrossMargin":   gross_margin if gross_margin is not None else gm_latest,
        "GMExpanding":   (gm_latest > gm_prior) if (gm_latest is not None and gm_prior is not None) else None,
        "RuleOf40":      rule40,
        "FCF":           fcf,
        "ForwardEps":    fwd_eps,
        "TrailingEps":   trail_eps,
        "AnalystRevise": c5,
        "c1": c1, "c2": c2, "c3": c3, "c4": c4, "c5": c5,
        "Score":         score,
        "Signal":        _signal(score),
        "notes":         notes,
    }


def screen_universe(universe: list, info_cache: dict = None) -> tuple:
    """
    Screen every ticker in `universe`. Returns (results, data_quality).

    results       : list of full result dicts (scored)
    data_quality  : list of {Ticker, Issue} rows for tickers with problems
    """
    info_cache = info_cache or {}
    results, data_quality = [], []

    for i, ticker in enumerate(universe, 1):
        log.info(f"  [{i}/{len(universe)}] screening {ticker}...")
        try:
            res = screen_ticker(ticker, info=info_cache.get(ticker))
        except Exception as e:
            res = {"Ticker": ticker, "error": str(e),
                   "Score": 0, "Signal": "🔴", "notes": [f"crash: {e}"]}

        if res.get("error"):
            data_quality.append({"Ticker": ticker, "Issue": res["error"]})
        elif res.get("notes"):
            data_quality.append({"Ticker": ticker, "Issue": "; ".join(res["notes"])})

        results.append(res)
        time.sleep(RATE_LIMIT_SLEEP)

    results.sort(key=lambda r: r.get("Score", 0), reverse=True)
    return results, data_quality
