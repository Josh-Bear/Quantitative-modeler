"""
Module 1: Data Pipeline (bl_spec/01_DATA_PIPELINE.md)

Acquires and stores all raw data for the rest of the pipeline:
  - S&P 500 ticker universe + GICS sector map (Wikipedia, current snapshot)
  - daily adjusted OHLCV per ticker (yfinance) → data/raw/prices/{ticker}.parquet
  - reconstructed daily market cap (Option A → Option B fallback) → mcap_history
  - data-quality report

No price data exists until this runs. Like the sibling bl_lstm_views, there is
no inline price fallback (14 years × 500 stocks is too large to inline); the raw
parquet files on disk ARE the cache for downstream modules.

Survivorship bias: the current S&P 500 list is applied retroactively to 2010.
Known limitation, disclosed in the final report (01 §5, 09 §1).
"""
from __future__ import annotations

import os
import time
import warnings
from typing import Optional

import numpy as np
import pandas as pd
import requests

from . import constants as C

_OHLCV_COLS = ["open", "high", "low", "close", "volume"]
_HEADERS = {  # default urllib UA gets a 403 from Wikipedia; spoof a browser
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
}


# ─────────────────────────────────────────────────────────────────────────────
# Ticker symbol helpers (Wikipedia uses BRK.B; yfinance wants BRK-B)
# ─────────────────────────────────────────────────────────────────────────────
def to_yf(ticker: str) -> str:
    """Normalise a Wikipedia/GICS symbol to the yfinance convention."""
    return ticker.replace(".", "-").strip()


# ─────────────────────────────────────────────────────────────────────────────
# 1. Universe + sector map  (01 §3.1, §3.4)
# ─────────────────────────────────────────────────────────────────────────────
def fetch_index_table(url: str, min_rows: int = 50) -> Optional[pd.DataFrame]:
    """Fetch a Wikipedia index-constituents table and normalise it to
    [ticker, gics_sector], or None on failure.

    Generalised (not hardcoded to table index 0) because the S&P 500 and S&P 100
    Wikipedia pages don't share a layout: the S&P 100 page has an infobox and a
    price-snapshot table ahead of the constituents table, and uses a plain
    "Sector" column where the S&P 500 page uses "GICS Sector". Search every table
    on the page for one with a Symbol + Sector-like column and >= min_rows rows,
    rather than assume a fixed position. Uses requests with a browser User-Agent
    (the default agent gets a 403), mirroring qqq_screener/universe.py.
    """
    try:
        import io
        resp = requests.get(url, headers=_HEADERS, timeout=20)
        resp.raise_for_status()
        # pandas >=2.1 treats a bare string as a path/URL — wrap HTML in StringIO.
        tables = pd.read_html(io.StringIO(resp.text))
        for df in tables:
            col_by_lower = {str(c).strip().lower(): c for c in df.columns}
            sym_col = col_by_lower.get("symbol")
            sec_col = col_by_lower.get("gics sector") or col_by_lower.get("sector")
            if sym_col is None or sec_col is None or len(df) < min_rows:
                continue
            out = df[[sym_col, sec_col]].rename(
                columns={sym_col: "ticker", sec_col: "gics_sector"})
            out["ticker"] = out["ticker"].astype(str).map(to_yf)
            return out.dropna(subset=["ticker"]).drop_duplicates("ticker").reset_index(drop=True)
        warnings.warn(f"[M1] no constituents table found at {url} "
                      f"(looked for a Symbol+Sector column with >= {min_rows} rows).")
        return None
    except Exception as e:  # noqa: BLE001 — never crash the pipeline on a fetch
        warnings.warn(f"[M1] Wikipedia index fetch failed ({url}): {e}")
        return None


def get_universe(universe: Optional[list[str]] = None) -> tuple[list[str], dict]:
    """Resolve (tickers, sector_map) for the run.

    universe=None  → live S&P 100 list + sector map from Wikipedia. DEVIATION from
                     00 §4 ("S&P 500, ~500 stocks") — the live/`--full` universe
                     was narrowed from S&P 500 to S&P 100, approved by Josh
                     2026-07-02 after a real --full (S&P 500) run took 15-20+
                     hours and had to be interrupted; see constants.py and
                     bl_spec/09_OPEN_DECISIONS.md §11. Dev profiles (quick/default)
                     are unaffected — they already pass a fixed small `universe`.
    universe=[...] → that fixed list (a dev profile); sectors resolved from the
                     Wikipedia table where present, else the inline fallback map,
                     else yfinance .info['sector'].
    """
    table = fetch_index_table(C.WIKI_SP100_URL, min_rows=50)
    wiki_map = dict(zip(table["ticker"], table["gics_sector"])) if table is not None else {}

    if universe is None:
        if table is None:
            warnings.warn("[M1] No live universe and no fixed list — "
                          "falling back to DEFAULT_UNIVERSE.")
            tickers = [to_yf(t) for t in C.DEFAULT_UNIVERSE]
        else:
            tickers = list(wiki_map.keys())
    else:
        tickers = [to_yf(t) for t in universe]

    sector_map: dict[str, str] = {}
    for t in tickers:
        if t in wiki_map:
            sector_map[t] = wiki_map[t]
        elif t in C.FALLBACK_SECTOR_MAP:
            sector_map[t] = C.FALLBACK_SECTOR_MAP[t]
        else:
            sector_map[t] = _yf_sector(t)
    return tickers, sector_map


def _yf_sector(ticker: str) -> Optional[str]:
    """Last-resort per-ticker sector lookup via yfinance .info (rate-limited)."""
    try:
        import yfinance as yf
        time.sleep(C.RATE_LIMIT_SLEEP)
        return yf.Ticker(ticker).info.get("sector")
    except Exception:  # noqa: BLE001
        return None


# ─────────────────────────────────────────────────────────────────────────────
# 2. OHLCV download  (01 §3.2)
# ─────────────────────────────────────────────────────────────────────────────
def download_prices(tickers: list[str], force: bool = False) -> list[str]:
    """Download daily adjusted OHLCV per ticker → data/raw/prices/{ticker}.parquet.

    Batched in chunks (bulk 500-ticker downloads are unreliable). Failures are
    logged to failed_tickers.log, never crash the run. Returns the tickers that
    were successfully stored. Already-cached tickers are skipped unless force.
    """
    import yfinance as yf

    C.ensure_dirs()
    failed: list[str] = []
    ok: list[str] = []

    todo = tickers if force else [
        t for t in tickers
        if not os.path.exists(os.path.join(C.RAW_PRICES_DIR, f"{t}.parquet"))
    ]
    cached = [t for t in tickers if t not in todo]
    ok.extend(cached)
    if cached:
        print(f"[M1] {len(cached)} tickers already cached, skipping download.")

    for i in range(0, len(todo), C.DOWNLOAD_CHUNK):
        chunk = todo[i:i + C.DOWNLOAD_CHUNK]
        print(f"[M1] downloading {i + 1}-{i + len(chunk)} / {len(todo)} …")
        try:
            raw = yf.download(
                chunk, start=C.DATA_START, end=None, group_by="ticker",
                auto_adjust=True, threads=True, progress=False,
            )
        except Exception as e:  # noqa: BLE001
            warnings.warn(f"[M1] chunk download failed ({chunk[:3]}…): {e}")
            failed.extend(chunk)
            continue

        for t in chunk:
            try:
                df = _extract_one(raw, t, single=(len(chunk) == 1))
                if df is None or df.empty:
                    failed.append(t)
                    continue
                df.to_parquet(os.path.join(C.RAW_PRICES_DIR, f"{t}.parquet"))
                ok.append(t)
            except Exception as e:  # noqa: BLE001
                warnings.warn(f"[M1] {t} extract/store failed: {e}")
                failed.append(t)

    if failed:
        with open(os.path.join(C.DATA_DIR, "failed_tickers.log"), "a") as fh:
            for t in failed:
                fh.write(f"{t}\n")
        print(f"[M1] {len(failed)} tickers failed (see failed_tickers.log).")
    return sorted(set(ok))


def _extract_one(raw: pd.DataFrame, ticker: str, single: bool) -> Optional[pd.DataFrame]:
    """Pull one ticker's OHLCV frame out of a (possibly multi-index) download."""
    if single:
        df = raw.copy()
    else:
        if ticker not in raw.columns.get_level_values(0):
            return None
        df = raw[ticker].copy()
    df.columns = [str(c).lower() for c in df.columns]
    keep = [c for c in _OHLCV_COLS if c in df.columns]
    df = df[keep].dropna(how="all")
    df.index.name = "date"
    return df.reset_index()


# ─────────────────────────────────────────────────────────────────────────────
# 3. Market cap reconstruction — Option A → Option B fallback  (01 §3.3, 09 §2)
# ─────────────────────────────────────────────────────────────────────────────
def reconstruct_mcap(tickers: list[str]) -> pd.DataFrame:
    """Reconstruct daily market cap per ticker.

    Option A (preferred): mcap(t) = sharesOutstanding × close(t), assuming shares
    are roughly constant over the window. Option B (fallback): static current
    mcap used for the whole history when shares are unavailable. Logs which
    tickers used the fallback; warns if the fallback exceeds 20% of tickers
    (09 §2 — the mcap-weighting in M5 may then be meaningfully distorted).
    """
    import yfinance as yf

    frames = []
    fallback_tickers: list[str] = []
    n = len(tickers)

    for i, t in enumerate(tickers, 1):
        if i % 50 == 0 or i == n:
            print(f"[M1] market cap {i}/{n} …", flush=True)
        prices = load_prices(t)
        if prices is None or prices.empty:
            continue
        close = prices.set_index("date")["close"]
        shares = None
        try:
            time.sleep(C.RATE_LIMIT_SLEEP)
            info = yf.Ticker(t).info
            shares = info.get("sharesOutstanding")
        except Exception:  # noqa: BLE001
            shares = None

        if shares and shares > 0:                       # Option A
            mcap = close * float(shares)
        else:                                           # Option B fallback
            fallback_tickers.append(t)
            static = None
            try:
                static = yf.Ticker(t).info.get("marketCap")
            except Exception:  # noqa: BLE001
                static = None
            if not static or static <= 0:
                continue
            mcap = pd.Series(float(static), index=close.index)

        frames.append(pd.DataFrame({"date": mcap.index, "ticker": t,
                                    "market_cap": mcap.values}))

    if fallback_tickers:
        frac = len(fallback_tickers) / max(len(tickers), 1)
        print(f"[M1] mcap Option B (static) used for {len(fallback_tickers)} "
              f"tickers ({frac:.0%}): {fallback_tickers[:10]}"
              f"{'…' if len(fallback_tickers) > 10 else ''}")
        if frac > 0.20:  # 09 §2 — revisit threshold
            warnings.warn(f"[M1] mcap fallback used for {frac:.0%} of tickers "
                          f"(>20%); M5 mcap-weighting may be distorted (09 §2).")

    if not frames:
        return pd.DataFrame(columns=["date", "ticker", "market_cap"])
    out = pd.concat(frames, ignore_index=True)
    out.attrs["fallback_tickers"] = fallback_tickers
    return out


# ─────────────────────────────────────────────────────────────────────────────
# 4. Data quality checks  (01 §4)
# ─────────────────────────────────────────────────────────────────────────────
def data_quality_report(tickers: list[str]) -> pd.DataFrame:
    """Per-ticker QA: start date, missing %, stale runs, extreme returns."""
    rows = []
    for t in tickers:
        df = load_prices(t)
        if df is None or df.empty:
            rows.append({"ticker": t, "start_date": None, "n_rows": 0,
                         "missing_pct": None, "max_stale_run": None,
                         "n_extreme_returns": None})
            continue
        s = df.set_index("date")["close"].sort_index()
        bdays = pd.bdate_range(s.index.min(), s.index.max())
        missing_pct = 1 - len(s) / max(len(bdays), 1)
        # longest run of identical close (stale prices / halt)
        same = (s.diff() == 0).astype(int)
        max_stale = _max_run(same.values)
        # single-day returns beyond ±50%
        rets = s.pct_change()
        n_extreme = int((rets.abs() > 0.50).sum())
        rows.append({
            "ticker": t,
            "start_date": s.index.min().date().isoformat(),
            "n_rows": len(s),
            "missing_pct": round(float(missing_pct), 4),
            "max_stale_run": int(max_stale),
            "n_extreme_returns": n_extreme,
        })
    rep = pd.DataFrame(rows)
    rep.to_csv(os.path.join(C.DATA_DIR, "data_quality_report.csv"), index=False)
    # flag the noteworthy ones (logged, not deleted, per 01 §4)
    bad = rep[(rep["missing_pct"].fillna(0) > 0.05) | (rep["max_stale_run"].fillna(0) > 10)]
    if not bad.empty:
        print(f"[M1] {len(bad)} tickers flagged in data-quality (>5% missing or "
              f">10-day stale run) — logged, not removed.")
    return rep


def _max_run(flags: np.ndarray) -> int:
    best = cur = 0
    for f in flags:
        cur = cur + 1 if f else 0
        best = max(best, cur)
    return best


# ─────────────────────────────────────────────────────────────────────────────
# Load helpers used by downstream modules
# ─────────────────────────────────────────────────────────────────────────────
def load_prices(ticker: str) -> Optional[pd.DataFrame]:
    """Read a ticker's full OHLCV frame (columns: date, open, high, low, close, volume)."""
    path = os.path.join(C.RAW_PRICES_DIR, f"{ticker}.parquet")
    if not os.path.exists(path):
        return None
    df = pd.read_parquet(path)
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date").reset_index(drop=True)


def load_close_series(ticker: str) -> Optional[pd.Series]:
    df = load_prices(ticker)
    if df is None:
        return None
    return df.set_index("date")["close"].sort_index()


def load_sector_map() -> dict:
    path = os.path.join(C.REFERENCE_DIR, "sector_map.csv")
    df = pd.read_csv(path)
    return dict(zip(df["ticker"], df["gics_sector"]))


def available_tickers() -> list[str]:
    if not os.path.isdir(C.RAW_PRICES_DIR):
        return []
    return sorted(f[:-8] for f in os.listdir(C.RAW_PRICES_DIR) if f.endswith(".parquet"))


# ─────────────────────────────────────────────────────────────────────────────
# Orchestration
# ─────────────────────────────────────────────────────────────────────────────
def run_data_pipeline(universe: Optional[list[str]] = None,
                      force: bool = False) -> dict:
    """Run M1 end-to-end and write the output contract (01 §6)."""
    C.ensure_dirs()
    print("[M1] resolving universe + sector map …")
    tickers, sector_map = get_universe(universe)
    print(f"[M1] {len(tickers)} tickers in universe.")

    ok = download_prices(tickers, force=force)
    sector_map = {t: s for t, s in sector_map.items() if t in ok}

    # reference outputs
    pd.DataFrame({"ticker": ok}).to_csv(
        os.path.join(C.REFERENCE_DIR, "ticker_universe.csv"), index=False)
    pd.DataFrame(
        [{"ticker": t, "gics_sector": sector_map.get(t)} for t in ok]
    ).to_csv(os.path.join(C.REFERENCE_DIR, "sector_map.csv"), index=False)

    print("[M1] reconstructing market cap …")
    mcap = reconstruct_mcap(ok)
    mcap.to_parquet(os.path.join(C.REFERENCE_DIR, "mcap_history.parquet"))

    print("[M1] running data-quality checks …")
    qa = data_quality_report(ok)

    # 09 §9 — confirm every GICS sector is represented with >=2 stocks
    _validate_sectors(sector_map)

    return {"tickers": ok, "sector_map": sector_map,
            "n_failed": len(tickers) - len(ok), "quality": qa}


def _validate_sectors(sector_map: dict) -> None:
    counts = pd.Series(list(sector_map.values())).value_counts()
    thin = [s for s in C.GICS_SECTORS if counts.get(s, 0) < C.N_PER_SECTOR]
    if thin:
        warnings.warn(f"[M1] sectors with <{C.N_PER_SECTOR} stocks: {thin} "
                      f"(09 §9 — edge-case handling in M4 will degrade these).")
