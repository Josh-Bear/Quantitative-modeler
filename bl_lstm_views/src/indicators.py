"""
indicators.py — the 8 technical indicators (BL_LSTM_Project_Summary.md §3.2),
computed in PURE pandas/numpy. No pandas_ta, no TA-Lib C library.

Each function takes/returns pandas Series aligned to a daily OHLCV frame whose
columns are lower-cased: open, high, low, close, volume.

    macd        Trend      EMA(12) - EMA(26)
    rsi         Momentum   14-period Wilder RSI
    squeeze_on  Volatility Bollinger band inside Keltner channel (0/1)
    bb_width    Volatility Bollinger band width  (upper - lower)
    kc_width    Volatility Keltner channel width (upper - lower)
    sq_momentum Momentum   TTM squeeze momentum (linreg endpoint of detrended price)
    obv         Volume     on-balance volume
    hilbert     Cycle      dominant cycle period (rolling-FFT approx of HT_DCPERIOD)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import constants as C


# ── building blocks ──────────────────────────────────────────────────────────
def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def _wilder(series: pd.Series, length: int) -> pd.Series:
    """Wilder's smoothing == EWM with alpha = 1/length."""
    return series.ewm(alpha=1.0 / length, adjust=False).mean()


def _true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr


# ── individual indicators ────────────────────────────────────────────────────
def macd(close: pd.Series, fast: int = 12, slow: int = 26) -> pd.Series:
    return _ema(close, fast) - _ema(close, slow)


def rsi(close: pd.Series, length: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = _wilder(gain, length)
    avg_loss = _wilder(loss, length)
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    out = 100.0 - 100.0 / (1.0 + rs)
    out[avg_loss == 0.0] = 100.0   # all-gains window → fully overbought
    return out


def bollinger(close: pd.Series, length: int = 20, std: float = 2.0):
    mid = close.rolling(length).mean()
    sd = close.rolling(length).std(ddof=0)
    upper = mid + std * sd
    lower = mid - std * sd
    return upper, lower


def keltner(high, low, close, length: int = 20, scalar: float = 1.5):
    mid = _ema(close, length)
    rng = _ema(_true_range(high, low, close), length)
    upper = mid + scalar * rng
    lower = mid - scalar * rng
    return upper, lower


def _linreg_endpoint(window: np.ndarray) -> float:
    """Value of the OLS line fitted over `window` evaluated at its last point.

    x is fixed at 0..L-1, so with xbar = mean(x): endpoint = ybar + slope*xbar.
    """
    L = window.shape[0]
    x = np.arange(L, dtype=float)
    xbar = x.mean()
    ybar = window.mean()
    sxx = ((x - xbar) ** 2).sum()
    if sxx == 0:
        return ybar
    slope = ((x - xbar) * (window - ybar)).sum() / sxx
    return ybar + slope * xbar


def sq_momentum(high, low, close, length: int = 20, linreg_length: int = 12) -> pd.Series:
    """TTM squeeze momentum: linreg endpoint of price minus its mid-range/EMA blend."""
    kc_mid = _ema(close, length)
    highest = high.rolling(length).max()
    lowest = low.rolling(length).min()
    detrended = close - ((highest + lowest) / 2.0 + kc_mid) / 2.0
    return detrended.rolling(linreg_length).apply(_linreg_endpoint, raw=True)


def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    direction = np.sign(close.diff().fillna(0.0))
    return (direction * volume).fillna(0.0).cumsum()


def hilbert_period(close: pd.Series, window: int = 30) -> pd.Series:
    """Dominant cycle period via rolling FFT — an approximation of TA-Lib's
    HT_DCPERIOD (which needs the C library). For each window we detrend, take the
    real FFT, and report 1 / (dominant non-DC frequency)."""
    vals = close.to_numpy(dtype=float)
    n = len(vals)
    out = np.full(n, np.nan)
    freqs = np.fft.rfftfreq(window)
    freqs[0] = np.inf  # guard the DC bin against division by zero
    for i in range(window, n):
        chunk = vals[i - window:i]
        spectrum = np.abs(np.fft.rfft(chunk - chunk.mean()))
        if spectrum.shape[0] <= 1:
            continue
        dom = np.argmax(spectrum[1:]) + 1   # skip DC component
        out[i] = 1.0 / freqs[dom]
    return pd.Series(out, index=close.index)


# ── assembly ─────────────────────────────────────────────────────────────────
def add_indicators(df: pd.DataFrame, hilbert_window: int = C.TIME_WINDOW) -> pd.DataFrame:
    """Return a copy of `df` (lower-cased OHLCV) with the 8 feature columns added."""
    out = df.copy()
    high, low, close, volume = out["high"], out["low"], out["close"], out["volume"]

    out["macd"] = macd(close)
    out["rsi"] = rsi(close)

    bb_upper, bb_lower = bollinger(close)
    kc_upper, kc_lower = keltner(high, low, close)
    out["bb_width"] = bb_upper - bb_lower
    out["kc_width"] = kc_upper - kc_lower
    out["squeeze_on"] = ((bb_upper < kc_upper) & (bb_lower > kc_lower)).astype(int)

    out["sq_momentum"] = sq_momentum(high, low, close)
    out["obv"] = obv(close, volume)
    out["hilbert"] = hilbert_period(close, window=hilbert_window)

    return out


def feature_frame(df: pd.DataFrame) -> pd.DataFrame:
    """OHLCV frame -> the 8 feature columns only, rows with any NaN dropped."""
    enriched = add_indicators(df)
    return enriched[C.FEATURES].dropna()
