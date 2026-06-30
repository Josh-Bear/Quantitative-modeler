"""
Module 2: Feature Engineering — the 8 technical indicators
(bl_spec/02_FEATURE_ENGINEERING.md)

Computes, per ticker per day, the 8 indicators the LSTM consumes:
    rsi, atr, macd_hist, keltner_pos, bb_pctb, squeeze_on, momentum_pct, ht_dcperiod

Library policy (02 §2): use `ta` for the indicators with a clean one-liner
(RSI, MACD histogram, ROC) to reduce bugs; hand-roll ATR / Keltner / Bollinger /
Squeeze so the band-based trio share *consistent* bounds (the squeeze is defined
by comparing the Bollinger and Keltner bands, so they must come from the same
formulas); HT_DCPERIOD comes from TA-Lib (the only source for it).

Output is RAW (unstandardised) — per-window z-scoring happens in M3 so it can
respect the walk-forward constraint (02 §4.2). Warm-up rows (NaN) are dropped
here so they never reach the model (02 §4.1).
"""
from __future__ import annotations

import os
import warnings
from typing import Optional

import numpy as np
import pandas as pd

from . import constants as C
from . import data_pipeline as dp

_OUT_COLS = ["date"] + C.FEATURES


# ─────────────────────────────────────────────────────────────────────────────
# Hand-rolled helpers (exact spec formulas, shared band bounds)
# ─────────────────────────────────────────────────────────────────────────────
def _true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    return pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)


def _atr(high, low, close, window: int) -> pd.Series:
    """ATR = rolling mean of True Range (02 §2.2 formula)."""
    return _true_range(high, low, close).rolling(window).mean()


# ─────────────────────────────────────────────────────────────────────────────
# Main per-ticker indicator computation
# ─────────────────────────────────────────────────────────────────────────────
def compute_indicators(ohlcv_df: pd.DataFrame) -> pd.DataFrame:
    """Input: one ticker's [date, open, high, low, close, volume], date-ascending.
    Output: [date, rsi, atr, macd_hist, keltner_pos, bb_pctb, squeeze_on,
             momentum_pct, ht_dcperiod] with warm-up NaN rows dropped.
    """
    import ta
    import talib

    df = ohlcv_df.sort_values("date").reset_index(drop=True)
    high, low, close = df["high"], df["low"], df["close"]

    out = pd.DataFrame({"date": df["date"]})

    # 2.1 RSI(14) — library
    out["rsi"] = ta.momentum.RSIIndicator(close, window=14).rsi()

    # 2.2 ATR(14) — hand-rolled rolling mean of TR (matches spec formula)
    out["atr"] = _atr(high, low, close, window=14)

    # 2.3 MACD histogram = MACD line - signal — library
    out["macd_hist"] = ta.trend.MACD(
        close, window_slow=26, window_fast=12, window_sign=9).macd_diff()

    # 2.4 Keltner channel position = (close - lower) / (upper - lower),
    #     middle = EMA(20), bands = middle ± 2·ATR(10)  (hand-rolled, shared
    #     with the squeeze below so the band comparison is consistent)
    kc_mid = close.ewm(span=20, adjust=False).mean()
    kc_atr = _atr(high, low, close, window=10)
    kc_upper = kc_mid + 2 * kc_atr
    kc_lower = kc_mid - 2 * kc_atr
    out["keltner_pos"] = (close - kc_lower) / (kc_upper - kc_lower)

    # 2.5 Bollinger %B = (close - lower) / (upper - lower),
    #     middle = SMA(20), bands = middle ± 2·std(20)
    bb_mid = close.rolling(20).mean()
    bb_std = close.rolling(20).std()
    bb_upper = bb_mid + 2 * bb_std
    bb_lower = bb_mid - 2 * bb_std
    out["bb_pctb"] = (close - bb_lower) / (bb_upper - bb_lower)

    # 2.6 TTM Squeeze on/off — BB inside KC ⇒ compression (0/1)
    out["squeeze_on"] = ((bb_upper < kc_upper) & (bb_lower > kc_lower)).astype(int)

    # 2.7 Momentum — normalised 10-day rate-of-change — library
    out["momentum_pct"] = ta.momentum.ROCIndicator(close, window=10).roc() / 100.0

    # 2.8 Hilbert transform dominant cycle period — TA-Lib (only source)
    out["ht_dcperiod"] = talib.HT_DCPERIOD(close.to_numpy(dtype="float64"))

    # 02 §4.1 — drop warm-up rows. First drop the leading WARMUP_DROP rows by
    # original position: this clears HT_DCPERIOD's *unstable* period (values are
    # present but unreliable for ~50-63 bars even after the hard-NaN warm-up).
    # Then dropna() removes any residual NaN, guaranteeing none reaches the LSTM.
    out = out.iloc[C.WARMUP_DROP:]
    out = out.replace([np.inf, -np.inf], np.nan).dropna().reset_index(drop=True)
    return out[_OUT_COLS]


# ─────────────────────────────────────────────────────────────────────────────
# Per-ticker driver + loaders
# ─────────────────────────────────────────────────────────────────────────────
def build_features(ticker: str, force: bool = False) -> Optional[pd.DataFrame]:
    """Compute and cache one ticker's features → data/features/{ticker}.parquet."""
    C.ensure_dirs()
    out_path = os.path.join(C.FEATURES_DIR, f"{ticker}.parquet")
    if os.path.exists(out_path) and not force:
        return pd.read_parquet(out_path)

    raw = dp.load_prices(ticker)
    if raw is None or len(raw) < C.WARMUP_DROP + C.INPUT_WINDOW + C.HORIZON:
        warnings.warn(f"[M2] {ticker}: insufficient price history, skipped.")
        return None
    feats = compute_indicators(raw)
    if feats.empty:
        warnings.warn(f"[M2] {ticker}: empty feature frame after warm-up drop.")
        return None
    feats.to_parquet(out_path, index=False)
    return feats


def load_features(ticker: str) -> Optional[pd.DataFrame]:
    path = os.path.join(C.FEATURES_DIR, f"{ticker}.parquet")
    if not os.path.exists(path):
        return None
    df = pd.read_parquet(path)
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date").reset_index(drop=True)


def run_feature_engineering(tickers: list[str], force: bool = False) -> list[str]:
    """Compute features for every ticker (skip-and-continue). Returns the
    tickers that produced a usable feature file."""
    ok = []
    for i, t in enumerate(tickers, 1):
        try:
            feats = build_features(t, force=force)
            if feats is not None and not feats.empty:
                ok.append(t)
        except Exception as e:  # noqa: BLE001
            warnings.warn(f"[M2] {t}: indicator computation failed: {e}")
        if i % 25 == 0:
            print(f"[M2] features {i}/{len(tickers)} …")
    print(f"[M2] features built for {len(ok)}/{len(tickers)} tickers.")
    return ok
