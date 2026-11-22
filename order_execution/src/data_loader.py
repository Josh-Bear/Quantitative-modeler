"""
data_loader.py — hourly bars → MarketData (wide frames: index = datetime, columns = tickers).

Input is LONG format, one or more CSV files (e.g. one per year):
    TICKER, DATE, ..., CLOSE_PRC, ..., TRADING_VALUE, TRADING_VOLUME
Column names are matched case-insensitively against a few aliases. Extra columns
(OPEN/HIGH/LOW, PE, ...) are ignored.

Cleaning:
  * keep only bars whose hour is in SESSION_HOURS (drops 14:00 and stray off-hours rows)
  * select TICKERS
  * a ticker with no row in a bar: close is forward-filled, value/volume = 0
    (nothing traded → the executor cannot fill in that bar)
  * leading bars before every selected ticker has a price are dropped

synthetic_prices() builds the same structure from GBM for running without data.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from . import constants as C

_DT_NAMES = ("date", "datetime", "timestamp_local", "time")
_TICKER_NAMES = ("ticker", "symbol", "stock", "code")
_CLOSE_NAMES = ("close_prc", "close", "last", "price")
_VALUE_NAMES = ("trading_value", "value", "turnover")
_VOLUME_NAMES = ("trading_volume", "volume", "vol")


@dataclass
class MarketData:
    close: pd.DataFrame     # close price per bar
    value: pd.DataFrame     # THB traded in the bar
    volume: pd.DataFrame    # shares traded in the bar
    info: dict


def _find(cols, names, what: str):
    low = {str(c).lower().strip(): c for c in cols}
    for n in names:
        if n in low:
            return low[n]
    raise ValueError(f"no {what} column found (looked for {names}); columns = {list(cols)}")


def data_files(root: Path = C.ROOT, pattern: str = C.DATA_GLOB) -> list[Path]:
    return sorted(root.glob(pattern))


def load_csv(paths: list[Path | str] | Path | str | None = None,
             tickers: list[str] | None = C.TICKERS, n_stocks: int = C.N_STOCKS,
             hours: list[int] = C.SESSION_HOURS) -> MarketData:
    if paths is None:
        paths = data_files()
    if isinstance(paths, (str, Path)):
        paths = [paths]
    paths = [Path(p) for p in paths]
    if not paths:
        raise FileNotFoundError(f"no data files matching {C.DATA_GLOB} in {C.ROOT}")

    raw = pd.concat([pd.read_csv(p) for p in paths], ignore_index=True)
    dt = _find(raw.columns, _DT_NAMES, "datetime")
    tk = _find(raw.columns, _TICKER_NAMES, "ticker")
    cl = _find(raw.columns, _CLOSE_NAMES, "close")
    va = _find(raw.columns, _VALUE_NAMES, "traded value")
    vo = _find(raw.columns, _VOLUME_NAMES, "traded volume")

    raw[dt] = pd.to_datetime(raw[dt])
    raw[tk] = raw[tk].astype(str).str.strip()
    info: dict = {"files": [p.name for p in paths], "rows_raw": len(raw),
                  "tickers_in_file": sorted(raw[tk].unique())}

    on_grid = raw[dt].dt.hour.isin(hours) & (raw[dt].dt.minute == 0)
    info["rows_off_grid_dropped"] = int((~on_grid).sum())
    raw = raw[on_grid]

    if tickers:
        missing = [t for t in tickers if t not in set(raw[tk])]
        if missing:
            raise ValueError(f"tickers not found in data: {missing}")
        sel = list(tickers)
    else:
        sel = sorted(raw[tk].unique())
        if len(sel) > n_stocks:
            info["warning"] = (f"data has {len(sel)} tickers; using the first {n_stocks}. "
                               "Set TICKERS in constants.py to choose.")
            sel = sel[:n_stocks]
    raw = raw[raw[tk].isin(sel)]
    if raw.duplicated([tk, dt]).any():
        raise ValueError("duplicate (ticker, datetime) rows in data")

    def wide(col):
        return raw.pivot(index=dt, columns=tk, values=col).reindex(columns=sel).sort_index()

    close, value, volume = wide(cl), wide(va), wide(vo)
    return _clean(close, value, volume, info)


def _clean(close: pd.DataFrame, value: pd.DataFrame, volume: pd.DataFrame, info: dict) -> MarketData:
    for df in (close, value, volume):
        df.index.name, df.columns.name = "datetime", None
    info["missing_bars"] = {c: int(close[c].isna().sum()) for c in close.columns}
    close = close.ffill().dropna(how="any")      # carry the last price; drop the leading warm-up
    if close.empty:
        raise ValueError("no bars where every selected ticker has a price")
    if (close <= 0).any().any():
        raise ValueError("non-positive prices in data")
    value = value.reindex(close.index).fillna(0.0).astype(float)
    volume = volume.reindex(close.index).fillna(0.0).astype(float)
    if (value < 0).any().any() or (volume < 0).any().any():
        raise ValueError("negative traded value / volume in data")
    info["rows_used"] = len(close)
    info["start"], info["end"] = str(close.index[0]), str(close.index[-1])
    info["tickers_used"] = list(close.columns)
    return MarketData(close, value, volume, info)


def synthetic_prices(tickers: dict[str, float] = C.SYNTHETIC_TICKERS, days: int = C.SYNTHETIC_DAYS,
                     sigma_annual: float = C.SYNTHETIC_SIGMA_ANNUAL,
                     seed: int = C.SYNTHETIC_SEED,
                     mean_value: float = C.SYNTHETIC_HOURLY_VALUE_THB) -> MarketData:
    """GBM hourly closes + lognormal traded value on the SESSION_HOURS grid."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2025-01-02", periods=days)
    idx = pd.DatetimeIndex([d + pd.Timedelta(hours=h) for d in dates for h in C.SESSION_HOURS],
                           name="datetime")
    bars_per_year = C.TRADING_DAYS_PER_YEAR * len(C.SESSION_HOURS)
    sig = sigma_annual / np.sqrt(bars_per_year)
    close, value = {}, {}
    for name, p0 in tickers.items():
        mu = rng.normal(0.0, 0.15) / bars_per_year
        r = rng.normal(mu - 0.5 * sig ** 2, sig, len(idx))
        close[name] = p0 * np.exp(np.cumsum(r))
        value[name] = mean_value * rng.lognormal(-0.125, 0.5, len(idx))   # E[lognormal] = 1
    close, value = pd.DataFrame(close, index=idx), pd.DataFrame(value, index=idx)
    info = {"files": ["synthetic GBM"], "rows_raw": len(idx), "tickers_in_file": list(tickers)}
    return _clean(close, value, value / close, info)


def bars_per_day(index: pd.DatetimeIndex) -> int:
    counts = pd.Series(1, index=index).groupby(index.normalize()).sum()
    return max(int(counts.median()), 1)
