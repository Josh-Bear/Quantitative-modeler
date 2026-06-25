"""
preprocessing.py — turn a raw OHLCV frame into model-ready tensors.

Pipeline geometry (BL_LSTM_Project_Summary.md §4, §5):
  • 8 indicator features per day (indicators.feature_frame)
  • MinMaxScaler fit on the TRAIN slice only (no look-ahead leakage), applied to all
  • LSTM input: sliding windows X:(samples, TIME_WINDOW, 8)
       target  Y:(samples, 8) = the scaled indicators HORIZON days after the window end
  • SVR is contemporaneous: scaled indicators(d) → scaled close(d). The forecast
    horizon lives entirely in the LSTM (which predicts indicators HORIZON days ahead);
    SVR is just a non-linear indicators→price decoder applied to those predictions.

Index bookkeeping: every window records `asof_idx` (the last day in the window — the
day we stand on) and `target_idx = asof_idx + HORIZON` (the day being forecast), plus
their dates, so views.py and backtest.py can line predictions up with realised prices.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler

from . import constants as C
from .indicators import add_indicators


@dataclass
class StockData:
    ticker: str
    dates: pd.DatetimeIndex
    feats_scaled: np.ndarray            # (n, 8)
    close_raw: np.ndarray               # (n,)
    ref_raw: np.ndarray                 # (n,)  SMA_REF(close) — the trend reference
    close_rel: np.ndarray              # (n,)  close/ref - 1  (stationary SVR target)
    feat_scaler: MinMaxScaler
    train_mask: np.ndarray
    val_mask: np.ndarray
    test_mask: np.ndarray
    windows: dict = field(default_factory=dict)


def _date_masks(dates: pd.DatetimeIndex):
    # DatetimeIndex comparisons already return numpy bool arrays.
    train = np.asarray((dates >= pd.Timestamp(C.TRAIN_START)) & (dates <= pd.Timestamp(C.TRAIN_END)))
    val = np.asarray((dates >= pd.Timestamp(C.VAL_START)) & (dates <= pd.Timestamp(C.VAL_END)))
    test = np.asarray((dates >= pd.Timestamp(C.TEST_START)) & (dates <= pd.Timestamp(C.TEST_END)))
    return train, val, test


def build_stock_dataset(ticker: str, ohlcv: pd.DataFrame) -> StockData:
    """Compute indicators, align close, fit train-only feature scaler, return arrays."""
    enriched = add_indicators(ohlcv).copy()
    enriched["ref"] = enriched["close"].rolling(C.REF_WINDOW).mean()
    enriched["close_rel"] = enriched["close"] / enriched["ref"] - 1.0

    cols = C.FEATURES + ["close", "ref", "close_rel"]
    frame = enriched[cols].dropna()
    dates = frame.index

    feats = frame[C.FEATURES].to_numpy(dtype=float)
    close = frame["close"].to_numpy(dtype=float)
    ref = frame["ref"].to_numpy(dtype=float)
    close_rel = frame["close_rel"].to_numpy(dtype=float)
    train_mask, val_mask, test_mask = _date_masks(dates)

    if train_mask.sum() < C.TIME_WINDOW + C.HORIZON + 1:
        raise ValueError(f"{ticker}: not enough training rows ({int(train_mask.sum())})")

    feat_scaler = MinMaxScaler().fit(feats[train_mask])

    sd = StockData(
        ticker=ticker,
        dates=dates,
        feats_scaled=feat_scaler.transform(feats),
        close_raw=close,
        ref_raw=ref,
        close_rel=close_rel,
        feat_scaler=feat_scaler,
        train_mask=train_mask,
        val_mask=val_mask,
        test_mask=test_mask,
    )
    sd.windows = make_windows(sd)
    if int(sd.windows["train"].sum()) == 0:
        raise ValueError(f"{ticker}: no usable training windows after indicator warm-up")
    return sd


def make_windows(sd: StockData, window: int = C.TIME_WINDOW, horizon: int = C.HORIZON) -> dict:
    """Build LSTM sliding windows over the full scaled series with index bookkeeping.

    X[i]      = feats_scaled[i : i+window]
    asof_idx  = i + window - 1          (the day we stand on)
    target_idx= asof_idx + horizon      (the day being forecast)
    Y[i]      = feats_scaled[target_idx]
    """
    feats = sd.feats_scaled
    n = len(feats)
    X, Y, asof_idx = [], [], []
    last_start = n - window - horizon
    for i in range(0, last_start + 1):
        a = i + window - 1
        t = a + horizon
        X.append(feats[i:i + window])
        Y.append(feats[t])
        asof_idx.append(a)

    X = np.asarray(X, dtype=np.float32)
    Y = np.asarray(Y, dtype=np.float32)
    asof_idx = np.asarray(asof_idx, dtype=int)
    target_idx = asof_idx + horizon

    asof_dates = sd.dates[asof_idx]
    # split each sample by the day we stand on (asof), so test windows are the
    # days we'd actually trade on during the test year.
    train = np.asarray(asof_dates <= pd.Timestamp(C.TRAIN_END))
    val = np.asarray((asof_dates >= pd.Timestamp(C.VAL_START)) &
                     (asof_dates <= pd.Timestamp(C.VAL_END)))
    test = np.asarray((asof_dates >= pd.Timestamp(C.TEST_START)) &
                      (asof_dates <= pd.Timestamp(C.TEST_END)))

    return {
        "X": X, "Y": Y,
        "asof_idx": asof_idx, "target_idx": target_idx,
        "asof_dates": asof_dates, "target_dates": sd.dates[target_idx],
        "train": train, "val": val, "test": test,
    }


def svr_training_data(sd: StockData):
    """Contemporaneous (scaled indicators(d) → close_rel(d)) over the train slice."""
    m = sd.train_mask
    return sd.feats_scaled[m], sd.close_rel[m]
