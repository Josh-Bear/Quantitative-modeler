"""
svr_model.py — SVR that decodes the 8 (scaled) indicators into a relative price.

Trained contemporaneously on the train slice: indicators(d) → close_rel(d), where
close_rel = close/SMA_REF(close) - 1 (a stationary target an RBF SVR can actually
learn — see constants.REF_WINDOW). At inference it is fed the LSTM's HORIZON-ahead
indicator forecast; the relative prediction is turned back into a price level using
the as-of trend reference, yielding a HORIZON-ahead price forecast (summary §4.2).
Hyperparameters from grid search: RBF kernel, C=5, ε=0.01.
"""
from __future__ import annotations

import numpy as np
from sklearn.svm import SVR

from . import constants as C
from .preprocessing import StockData, svr_training_data


def train_close_svr(sd: StockData) -> SVR:
    """Fit SVR(scaled indicators(d) → close_rel(d)) on the train slice."""
    X, y = svr_training_data(sd)
    svr = SVR(kernel=C.SVR_KERNEL, C=C.SVR_C, epsilon=C.SVR_EPSILON)
    svr.fit(X, y)
    return svr


def predict_price(svr: SVR, sd: StockData, scaled_indicators: np.ndarray,
                  ref_asof) -> np.ndarray:
    """Predicted close price = ref_asof × (1 + predicted relative deviation).

    `ref_asof` is the trend reference on the day we stand on (scalar for a single
    forecast, or a per-sample array); it carries the current price level forward."""
    scaled_indicators = np.atleast_2d(np.asarray(scaled_indicators, dtype=float))
    rel_hat = svr.predict(scaled_indicators)
    return np.asarray(ref_asof, dtype=float) * (1.0 + rel_hat)


def train_fit_mse(svr: SVR, sd: StockData) -> float:
    """In-sample fit MSE on the train slice (close_rel space) — a sanity diagnostic."""
    X, y = svr_training_data(sd)
    return float(((svr.predict(X) - y) ** 2).mean())
