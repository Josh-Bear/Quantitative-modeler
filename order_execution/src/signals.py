"""
signals.py — SMA crossover + RSI filter on hourly closes.

Every signal is an EVENT (fires once), not a state, so a stock does not get the
same order every hour while a condition persists:

  BUY   SMA_fast crossed above SMA_slow within the last BUY_CONFIRM_BARS bars,
        fast is still above slow, RSI < RSI_BUY_MAX, and this cross has not
        already produced a BUY.
  SELL  SMA_fast crosses below SMA_slow, OR RSI crosses up through RSI_SELL.
  HOLD  otherwise.

Size: Δw = clip(K_DW × |Close − SMA_slow| / ATR, DW_MIN, DW_MAX), where ATR is
the mean |ΔClose| (Close-only proxy). |SMA_fast − SMA_slow| is deliberately not
used: it is ≈ 0 exactly at a crossover.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import constants as C

BUY, HOLD, SELL = 1, 0, -1
LABEL = {BUY: "BUY", HOLD: "HOLD", SELL: "SELL"}


# ported from bl_lstm_views/src/indicators.py (kept local so this model is self-contained)
def _wilder(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(alpha=1.0 / length, adjust=False).mean()


def rsi(close: pd.Series, length: int = C.RSI_LEN) -> pd.Series:
    delta = close.diff()
    avg_gain = _wilder(delta.clip(lower=0.0), length)
    avg_loss = _wilder((-delta).clip(lower=0.0), length)
    out = 100.0 - 100.0 / (1.0 + avg_gain / avg_loss.replace(0.0, np.nan))
    out[(avg_loss == 0.0) & (avg_gain > 0.0)] = 100.0
    out[(avg_loss == 0.0) & (avg_gain == 0.0)] = 50.0   # flat price → neutral
    out.iloc[:length] = np.nan                          # warm-up
    return out


def atr_close(close: pd.Series, length: int = C.ATR_LEN) -> pd.Series:
    return close.diff().abs().rolling(length).mean()


def compute_signals(close: pd.Series) -> pd.DataFrame:
    """Indicators + signal for one ticker. Index = close.index."""
    fast = close.rolling(C.SMA_FAST).mean()
    slow = close.rolling(C.SMA_SLOW).mean()
    r = rsi(close)
    atr = atr_close(close)

    above = (fast > slow).to_numpy()
    valid = (slow.notna() & slow.shift(1).notna() & r.notna()).to_numpy()
    prev_above = np.r_[False, above[:-1]]
    cross_up = valid & above & ~prev_above
    cross_dn = valid & ~above & prev_above
    rv = r.to_numpy()
    prev_r = np.r_[np.nan, rv[:-1]]
    rsi_x_sell = valid & (rv > C.RSI_SELL) & (prev_r <= C.RSI_SELL)

    sig = np.zeros(len(close), dtype=int)
    armed_left = 0                    # bars left in the BUY confirm window
    for i in range(len(close)):
        if cross_up[i]:
            armed_left = C.BUY_CONFIRM_BARS
        if cross_dn[i] or rsi_x_sell[i]:
            sig[i] = SELL
            armed_left = 0            # any SELL cancels a pending BUY
        elif armed_left > 0 and above[i] and rv[i] < C.RSI_BUY_MAX:
            sig[i] = BUY
            armed_left = 0            # one BUY per cross-up
        if armed_left > 0:
            armed_left -= 1

    with np.errstate(divide="ignore", invalid="ignore"):
        strength = (close - slow).abs().to_numpy() / atr.to_numpy()
    strength = np.where(np.isfinite(strength), strength, 0.0)
    dw = np.clip(C.K_DW * strength, C.DW_MIN, C.DW_MAX)

    return pd.DataFrame({
        "close": close, "sma_fast": fast, "sma_slow": slow, "rsi": r, "atr": atr,
        "strength": strength, "signal_code": sig,
        "signal": [LABEL[s] for s in sig], "dw": np.where(sig != HOLD, dw, 0.0),
    }, index=close.index)


def compute_all(prices: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {t: compute_signals(prices[t]) for t in prices.columns}


def signals_long(sig: dict[str, pd.DataFrame], only_events: bool = False) -> pd.DataFrame:
    frames = []
    for t, df in sig.items():
        d = df.reset_index().assign(ticker=t)
        if only_events:
            d = d[d["signal_code"] != HOLD]
        frames.append(d)
    out = pd.concat(frames, ignore_index=True)
    cols = ["datetime", "ticker", "signal", "dw", "close", "sma_fast", "sma_slow", "rsi", "atr", "strength"]
    return out[cols].sort_values(["datetime", "ticker"]).reset_index(drop=True)
