"""
data.py — hourly SET50 bars → everything the experiment needs, with no look-ahead.

  close, value, volume, vwap   bars × TICKERS (the 10 locked names)
  sigma                        ex-ante hourly σ of close returns at each bar (jumps excluded)
  jump                         |hourly return| > JUMP_FILTER (unadjusted corporate actions)
  adv                          days × tickers: mean daily traded value over the PREVIOUS ADV_DAYS days
  profile                      days × bar hours: VWAP volume profile known at the open of each day —
                               mean hourly share of daily value, pooled over TICKERS, over the
                               previous PROFILE_DAYS full trading days (rows sum to 1)

Bar VWAP = TRADING_VALUE / TRADING_VOLUME, clipped into the bar's [low, high].
A ticker with no row in a bar has value = volume = 0 (nothing can trade there);
its close is forward-filled only after its first observation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from . import constants as C

_COLS = {"TICKER": "ticker", "DATE": "dt", "CLOSE_PRC": "close", "LOW_PRC": "low",
         "HIGH_PRC": "high", "TRADING_VALUE": "value", "TRADING_VOLUME": "volume"}


@dataclass
class Market:
    close: pd.DataFrame
    value: pd.DataFrame
    volume: pd.DataFrame
    vwap: pd.DataFrame
    sigma: pd.DataFrame
    jump: pd.DataFrame
    adv: pd.DataFrame
    profile: pd.DataFrame
    info: dict = field(default_factory=dict)

    @property
    def tickers(self) -> list[str]:
        return list(self.close.columns)

    @property
    def hours(self) -> np.ndarray:
        return self.close.index.hour.to_numpy()

    @property
    def days(self) -> pd.DatetimeIndex:
        return self.close.index.normalize()


def data_files(directory: Path = C.DATA_DIR, pattern: str = C.DATA_GLOB) -> list[Path]:
    return sorted(Path(directory).glob(pattern))


def read_bars(paths: list[Path] | None = None, tickers: list[str] | None = C.TICKERS,
              hours: list[int] = C.SESSION_HOURS) -> tuple[pd.DataFrame, dict]:
    """Long rows on the bar grid for `tickers`: ticker, dt, close, low, high, value, volume."""
    paths = data_files() if paths is None else [Path(p) for p in paths]
    if not paths:
        raise FileNotFoundError(f"no {C.DATA_GLOB} in {C.DATA_DIR}")
    raw = pd.concat([pd.read_csv(p, usecols=list(_COLS)) for p in paths], ignore_index=True)
    raw = raw.rename(columns=_COLS)
    raw["dt"] = pd.to_datetime(raw["dt"])
    raw["ticker"] = raw["ticker"].astype(str).str.strip()
    info = {"files": [p.name for p in paths], "rows_raw": len(raw)}
    if tickers:
        missing = sorted(set(tickers) - set(raw["ticker"]))
        if missing:
            raise ValueError(f"tickers not in data: {missing}")
        raw = raw[raw["ticker"].isin(tickers)]
    on_grid = raw["dt"].dt.hour.isin(hours) & (raw["dt"].dt.minute == 0)
    info["rows_off_grid"] = int((~on_grid).sum())
    raw = raw[on_grid]
    if raw.duplicated(["ticker", "dt"]).any():
        raise ValueError("duplicate (ticker, datetime) rows")
    if (raw["close"] <= 0).any() or (raw[["value", "volume"]] < 0).any().any():
        raise ValueError("non-positive price or negative value/volume")
    return raw.reset_index(drop=True), info


def build_market(bars: pd.DataFrame, info: dict | None = None,
                 tickers: list[str] | None = C.TICKERS) -> Market:
    info = dict(info or {})

    def wide(col):
        w = bars.pivot(index="dt", columns="ticker", values=col).sort_index()
        if tickers:
            w = w.reindex(columns=[t for t in tickers if t in w.columns])
        w.index.name, w.columns.name = "datetime", None
        return w

    close = wide("close").ffill()                    # NaN before a ticker's first bar stays NaN
    value = wide("value").fillna(0.0)
    volume = wide("volume").fillna(0.0)
    low, high = wide("low"), wide("high")
    with np.errstate(divide="ignore", invalid="ignore"):
        raw_vwap = value / volume.where(volume > 0)
    vwap = raw_vwap.clip(lower=low, upper=high)

    ret = close.pct_change(fill_method=None)
    jump = ret.abs() > C.JUMP_FILTER
    sigma = ret.mask(jump).rolling(C.SIGMA_BARS, min_periods=30).std()   # returns up to and incl. bar t

    daily = value.groupby(value.index.normalize()).sum()
    adv = daily.rolling(C.ADV_DAYS, min_periods=C.ADV_DAYS).mean().shift(1)   # as of the day's open

    profile = rolling_profile(value, close)

    info.update({
        "bars": len(close), "tickers": list(close.columns),
        "start": str(close.index[0]), "end": str(close.index[-1]),
        "jump_bars": int(jump.sum().sum()),
        "vwap_clipped_share": float((raw_vwap != vwap).where(volume > 0).stack().mean()),
        "first_profile_day": str(profile.dropna().index[0].date()) if profile.notna().any().any() else None,
    })
    return Market(close, value, volume, vwap, sigma, jump, adv, profile, info)


def rolling_profile(value: pd.DataFrame, close: pd.DataFrame, days: int = C.PROFILE_DAYS) -> pd.DataFrame:
    """Profile row for day d = mean of the pooled hourly shares of the last `days` FULL
    trading days strictly before d (a full day has all SESSION_HOURS bars)."""
    n_hours = len(C.SESSION_HOURS)
    day = value.index.normalize()
    v = value.where(close.notna())                                 # ignore a ticker before it lists
    per_day = v.groupby(day).transform("sum")
    share = v / per_day.where(per_day > 0)
    pooled = share.mean(axis=1)                                    # mean over tickers, per bar
    full = pd.Series(1, index=value.index).groupby(day).transform("sum") == n_hours
    daily = pooled[full].groupby([day[full], value.index.hour[full]]).first().unstack()
    daily = daily.reindex(columns=C.SESSION_HOURS)
    roll = daily.rolling(days, min_periods=days).mean()            # includes the day itself …
    all_days = pd.DatetimeIndex(day.unique())
    prof = roll.reindex(all_days).ffill().shift(1)                 # … so shift: known at d's open
    prof.index.name, prof.columns.name = "day", "hour"
    return prof.div(prof.sum(axis=1), axis=0)


def load_market(paths: list[Path] | None = None) -> Market:
    bars, info = read_bars(paths)
    return build_market(bars, info)
