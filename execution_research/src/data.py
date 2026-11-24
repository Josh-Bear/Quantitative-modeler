"""
data.py — hourly SET50 bars → everything the experiment needs, with no look-ahead.

  close, value, volume, vwap   bars × tickers (all names in the files)
  sigma                        ex-ante hourly σ of close returns at each bar (jumps excluded)
  jump                         |hourly return| > JUMP_FILTER (unadjusted corporate actions)
  adv                          days × tickers: mean daily traded value over the PREVIOUS ADV_DAYS days
  top                          days × tickers: point-in-time Top-N by adv
  profile                      share of a day's traded value in each bar hour, IN-SAMPLE only

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
    top: pd.DataFrame
    profile: pd.Series
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


def read_bars(paths: list[Path] | None = None, hours: list[int] = C.SESSION_HOURS) -> tuple[pd.DataFrame, dict]:
    """Long rows on the bar grid: ticker, dt, close, low, high, value, volume."""
    paths = data_files() if paths is None else [Path(p) for p in paths]
    if not paths:
        raise FileNotFoundError(f"no {C.DATA_GLOB} in {C.DATA_DIR}")
    raw = pd.concat([pd.read_csv(p, usecols=list(_COLS)) for p in paths], ignore_index=True)
    raw = raw.rename(columns=_COLS)
    raw["dt"] = pd.to_datetime(raw["dt"])
    raw["ticker"] = raw["ticker"].astype(str).str.strip()
    on_grid = raw["dt"].dt.hour.isin(hours) & (raw["dt"].dt.minute == 0)
    info = {"files": [p.name for p in paths], "rows_raw": len(raw), "rows_off_grid": int((~on_grid).sum())}
    raw = raw[on_grid]
    if raw.duplicated(["ticker", "dt"]).any():
        raise ValueError("duplicate (ticker, datetime) rows")
    if (raw["close"] <= 0).any() or (raw[["value", "volume"]] < 0).any().any():
        raise ValueError("non-positive price or negative value/volume")
    return raw.reset_index(drop=True), info


def build_market(bars: pd.DataFrame, info: dict | None = None,
                 in_sample_end: str = C.IN_SAMPLE_END) -> Market:
    info = dict(info or {})

    def wide(col):
        w = bars.pivot(index="dt", columns="ticker", values=col).sort_index()
        w.index.name, w.columns.name = "datetime", None
        return w

    close = wide("close").ffill()                    # NaN before a ticker's first bar stays NaN
    value = wide("value").fillna(0.0)
    volume = wide("volume").fillna(0.0)
    low, high = wide("low"), wide("high")
    with np.errstate(divide="ignore", invalid="ignore"):
        vwap = (value / volume.where(volume > 0)).clip(lower=low, upper=high)

    ret = close.pct_change(fill_method=None)
    jump = ret.abs() > C.JUMP_FILTER
    clean = ret.mask(jump)
    sigma = clean.rolling(C.SIGMA_BARS, min_periods=30).std()      # uses returns up to and incl. bar t

    daily = value.groupby(value.index.normalize()).sum()
    adv = daily.rolling(C.ADV_DAYS, min_periods=C.ADV_DAYS).mean().shift(1)   # as of the day's open
    rank = adv.rank(axis=1, ascending=False, method="first")
    top = rank <= C.TOP_N

    profile = volume_profile(value, close, in_sample_end)

    info.update({
        "bars": len(close), "tickers": close.shape[1],
        "start": str(close.index[0]), "end": str(close.index[-1]),
        "jump_bars": int(jump.sum().sum()),
        "vwap_clipped_share": float(((value / volume.where(volume > 0)) != vwap).where(volume > 0).mean().mean()),
    })
    return Market(close, value, volume, vwap, sigma, jump, adv, top, profile, info)


def volume_profile(value: pd.DataFrame, close: pd.DataFrame, in_sample_end: str) -> pd.Series:
    """Mean share of a ticker-day's traded value falling in each bar hour (in-sample, full days only)."""
    v = value.loc[:in_sample_end]
    v = v.where(close.loc[:in_sample_end].notna())
    day = v.index.normalize()
    per_day = v.groupby(day).transform("sum")
    share = (v / per_day.where(per_day > 0))
    n_bars = v.notna().groupby(day).transform("sum")
    share = share.where(n_bars == len(C.SESSION_HOURS))
    prof = share.groupby(share.index.hour).mean().mean(axis=1)
    prof = prof.reindex(C.SESSION_HOURS).fillna(0.0)
    return prof / prof.sum()


def load_market(paths: list[Path] | None = None) -> Market:
    bars, info = read_bars(paths)
    return build_market(bars, info)
