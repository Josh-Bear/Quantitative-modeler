"""
fetch_data.py — live data pipeline.

Downloads daily OHLCV (yfinance) + market caps, and caches each ticker to
output/cache/ as CSV. On a failed/empty download it falls back to that cache, so
repeat runs work offline. (This is the one intentional departure from the repo's
"hardcoded constants.py fallback" rule — 14 years of daily OHLCV across the
universe is far too large to inline. See README.)

All frames use lower-cased columns: open, high, low, close, volume.
"""
from __future__ import annotations

import json
import os
import time

import pandas as pd
import yfinance as yf

from . import constants as C


def _cache_path(ticker: str, start: str, end: str) -> str:
    safe = f"{ticker}_{start}_{end}.csv".replace(":", "-")
    return os.path.join(C.CACHE_DIR, safe)


def _normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    """yfinance returns either flat or (field, ticker) MultiIndex columns."""
    if isinstance(df.columns, pd.MultiIndex):
        df = df.copy()
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns={c: str(c).lower() for c in df.columns})
    keep = [c for c in ["open", "high", "low", "close", "volume"] if c in df.columns]
    return df[keep]


def _save_cache(ticker: str, start: str, end: str, df: pd.DataFrame) -> None:
    os.makedirs(C.CACHE_DIR, exist_ok=True)
    df.to_csv(_cache_path(ticker, start, end))


def _load_cache(ticker: str, start: str, end: str) -> pd.DataFrame | None:
    path = _cache_path(ticker, start, end)
    if not os.path.exists(path):
        return None
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    return df if not df.empty else None


def download_prices(ticker: str, start: str, end: str, use_cache: bool = True) -> pd.DataFrame | None:
    """Daily OHLCV for one ticker; cache-backed. Returns None if unavailable."""
    try:
        raw = yf.download(
            ticker, start=start, end=end,
            interval="1d", auto_adjust=True, progress=False,
        )
        if raw is not None and not raw.empty:
            df = _normalise_columns(raw).dropna(how="all")
            if not df.empty:
                _save_cache(ticker, start, end, df)
                print(f"  ✅  {ticker}: {len(df)} daily bars")
                return df
        print(f"  ⚠️   {ticker}: empty download — trying cache")
    except Exception as e:  # network / yfinance hiccup
        print(f"  ❌  {ticker}: {e} — trying cache")

    if use_cache:
        cached = _load_cache(ticker, start, end)
        if cached is not None:
            print(f"  ♻️   {ticker}: {len(cached)} bars from cache")
            return cached
    return None


def fetch_market_caps(tickers: list[str], use_cache: bool = True) -> dict[str, float]:
    """marketCap per ticker (0 if unavailable). Cached to output/cache/market_caps.json."""
    cache_file = os.path.join(C.CACHE_DIR, "market_caps.json")
    cached: dict[str, float] = {}
    if use_cache and os.path.exists(cache_file):
        try:
            cached = json.load(open(cache_file))
        except Exception:
            cached = {}

    caps: dict[str, float] = {}
    for t in tickers:
        cap = 0.0
        try:
            info = yf.Ticker(t).info or {}
            cap = float(info.get("marketCap") or 0.0)
        except Exception:
            cap = 0.0
        if cap <= 0 and t in cached:        # fall back to last known cap
            cap = float(cached[t])
        caps[t] = cap
        time.sleep(C.RATE_LIMIT_SLEEP)

    merged = {**cached, **{k: v for k, v in caps.items() if v > 0}}
    try:
        os.makedirs(C.CACHE_DIR, exist_ok=True)
        json.dump(merged, open(cache_file, "w"), indent=2)
    except Exception:
        pass
    return caps


def fetch(tickers: list[str], start: str = C.DATA_START, end: str = C.DATA_END,
          with_market_caps: bool = True) -> dict:
    """Fetch OHLCV for `tickers` (+ market caps). Returns
    {prices: {t: df}, market_caps: {t: float}, errors: {t: str}}."""
    print(f"  ↗  Fetching {tickers}  ({start} → {end})")
    prices, errors = {}, {}
    for t in tickers:
        df = download_prices(t, start, end)
        if df is None or df.empty:
            errors[t] = "no usable price data (download + cache failed)"
            continue
        prices[t] = df
        time.sleep(C.RATE_LIMIT_SLEEP)

    market_caps = fetch_market_caps(list(prices.keys())) if with_market_caps else {}
    return {"prices": prices, "market_caps": market_caps, "errors": errors}
