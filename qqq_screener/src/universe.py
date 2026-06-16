"""
QQQ High Growth Screener — Universe Builder
=============================================
Pulls NASDAQ-100 constituents from Wikipedia, ranks them by live market
cap from yfinance, and filters to the configured rank window.

`info` dicts fetched here are cached and handed back so the screener can
reuse them instead of re-hitting yfinance for the same tickers.
"""

import io
import time
import logging

import pandas as pd

from constants import (
    WIKI_URL, FALLBACK_NASDAQ100, RANK_MIN, RANK_MAX, RATE_LIMIT_SLEEP,
)

log = logging.getLogger("universe")

# Wikipedia 403s the default urllib user-agent, so send a browser one.
_WIKI_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; QQQScreener/1.0)"}


def fetch_constituents() -> list:
    """Return NASDAQ-100 tickers from Wikipedia, or the hardcoded fallback."""
    try:
        import requests
        resp = requests.get(WIKI_URL, headers=_WIKI_HEADERS, timeout=15)
        resp.raise_for_status()
        tables = pd.read_html(io.StringIO(resp.text))
        for t in tables:
            cols = [str(c) for c in t.columns]
            for key in ("Ticker", "Symbol"):
                match = next((c for c in cols if key in c), None)
                if match is not None:
                    tickers = (
                        t[match].astype(str).str.strip().str.upper().tolist()
                    )
                    tickers = [tk for tk in tickers if tk and tk != "NAN"]
                    if len(tickers) >= 80:   # sanity check on table shape
                        log.info(f"Fetched {len(tickers)} tickers from Wikipedia")
                        return sorted(set(tickers))
        log.warning("No usable Ticker/Symbol column found; using fallback list")
    except Exception as e:
        log.warning(f"Wikipedia fetch failed ({e}); using fallback list")

    return sorted(set(FALLBACK_NASDAQ100))


def build_universe() -> tuple:
    """
    Rank constituents by market cap and filter to [RANK_MIN, RANK_MAX].

    Returns
    -------
    (universe, ranked_df, info_cache)
        universe   : list[str]        tickers in the rank window
        ranked_df  : pd.DataFrame      Ticker / MarketCap / Rank, all tickers
        info_cache : dict[str, dict]   yfinance .info per ticker (reusable)
    """
    import yfinance as yf

    tickers = fetch_constituents()
    log.info(f"Ranking {len(tickers)} tickers by market cap...")

    market_caps = {}
    info_cache = {}
    for i, ticker in enumerate(tickers, 1):
        try:
            info = yf.Ticker(ticker).info
            info_cache[ticker] = info
            market_caps[ticker] = info.get("marketCap") or 0
        except Exception as e:
            log.warning(f"  {ticker}: market cap fetch failed ({e})")
            info_cache[ticker] = {}
            market_caps[ticker] = 0
        if i % 20 == 0:
            log.info(f"  ...ranked {i}/{len(tickers)}")
        time.sleep(RATE_LIMIT_SLEEP)

    ranked_df = (
        pd.DataFrame(list(market_caps.items()), columns=["Ticker", "MarketCap"])
        .sort_values("MarketCap", ascending=False)
        .reset_index(drop=True)
    )
    ranked_df["Rank"] = ranked_df.index + 1

    universe = ranked_df[
        (ranked_df["Rank"] >= RANK_MIN) & (ranked_df["Rank"] <= RANK_MAX)
    ]["Ticker"].tolist()

    log.info(f"Universe: {len(universe)} tickers (rank {RANK_MIN}-{RANK_MAX})")
    return universe, ranked_df, info_cache
