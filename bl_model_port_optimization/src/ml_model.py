"""
Module 3: ML Model — LSTM (feature extractor) → SVR, per stock
(bl_spec/03_ML_MODEL.md)

For one stock at one rebalance date, using ONLY the rolling 10-year window of
features ending before that date (no look-ahead, 00 §5.1):

  1. Build 63-day input windows + 63-day-forward-return targets (overlapping,
     stride 1). Targets whose 63-day-ahead close falls on/after the rebalance
     date are dropped — using them would peek past `t` (00 §5.1).
  2. Chronological 80/20 train/val split (never shuffled — 03 §2).
  3. Standardise the 8 indicators with a z-score scaler fit on the TRAIN slice
     only (02 §4.2 / 03), applied to val + the prediction window.
  4. Train the LSTM end-to-end with a linear head (Option A, 09 §5), then discard
     the head and use the final hidden state as a fixed feature vector.
  5. Train the SVR (RBF) on train hidden states → predict the 63-day return.
  6. ω_i = variance of SVR residuals on the VALIDATION set (03 §5 — never train).
  7. Predict r_hat for the most recent 63-day window (ending at reb_date − 1).

`train_and_predict_at_date(ticker, reb_date)` is the unit of work M7 calls per
stock per rebalance.
"""
from __future__ import annotations

import warnings
from datetime import date
from typing import Optional

import numpy as np
import pandas as pd

from . import constants as C
from . import data_pipeline as dp
from . import features as ft


# ─────────────────────────────────────────────────────────────────────────────
# Torch is imported lazily so the lighter modules (M4-M6, test.py) don't need it.
# ─────────────────────────────────────────────────────────────────────────────
def _torch():
    import torch
    return torch


def get_device(prefer: str = "cpu"):
    """Resolve a torch device. Default 'cpu' — the backtest parallelises across
    stocks with CPU workers (07 §5), and MPS/multiprocessing interact badly.
    Pass prefer='mps' for single-stock notebook use."""
    torch = _torch()
    if prefer == "mps" and torch.backends.mps.is_available():
        return torch.device("mps")
    if prefer == "cuda" and torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


# ─────────────────────────────────────────────────────────────────────────────
# Dataset construction (the no-look-ahead heart of the module)
# ─────────────────────────────────────────────────────────────────────────────
def build_training_data(ticker: str, reb_date, min_samples: int = 100) -> Optional[dict]:
    """Build standardised LSTM windows + 63-day targets for one (ticker, date).

    Returns a dict of arrays, or None if there isn't enough usable history.
    All data is strictly before `reb_date`; targets needing data on/after it
    are dropped.
    """
    reb_ts = pd.Timestamp(reb_date)
    win_start = reb_ts - pd.DateOffset(years=C.ROLLING_WINDOW_YEARS)

    feats = ft.load_features(ticker)
    if feats is None:
        return None

    # Slice to the rolling window, strictly before the rebalance date.
    feats = feats[(feats["date"] >= win_start) & (feats["date"] < reb_ts)]
    feats = feats.reset_index(drop=True)
    if len(feats) < C.INPUT_WINDOW + C.HORIZON + min_samples:
        return None

    # Align close (for the forward-return target) onto the feature dates.
    close = dp.load_close_series(ticker)
    if close is None:
        return None
    close = close.reindex(feats["date"]).to_numpy(dtype="float64")
    if np.isnan(close).any():
        # a feature date with no matching close (shouldn't happen) — bail safely
        return None

    feat_mat = feats[C.FEATURES].to_numpy(dtype="float64")
    n = len(feats)
    w, h = C.INPUT_WINDOW, C.HORIZON

    # As-of positions p that have a full 63-day window behind them: p in [w-1, n-1].
    # Target(p) = close[p+h]/close[p] - 1, valid only if p+h <= n-1 (the forward
    # close is still inside the pre-rebalance slice → no look-ahead).
    asof_positions = np.arange(w - 1, n)
    valid = asof_positions + h <= n - 1
    sample_pos = asof_positions[valid]                  # have a target
    target = close[sample_pos + h] / close[sample_pos] - 1.0
    if len(sample_pos) < min_samples:
        return None

    # Chronological 80/20 split on the as-of ordering (03 §2 — no shuffle).
    n_train = int((1 - C.VAL_FRACTION) * len(sample_pos))
    if n_train < 30 or len(sample_pos) - n_train < 10:
        return None
    train_pos, val_pos = sample_pos[:n_train], sample_pos[n_train:]
    cutoff = int(train_pos[-1])                         # last row seen in training

    # Standardise: fit z-score ONLY on rows up to the last training as-of (02 §4.2).
    from sklearn.preprocessing import StandardScaler
    scaler = StandardScaler().fit(feat_mat[: cutoff + 1])
    feat_std = scaler.transform(feat_mat)

    def windows(positions):
        # window for as-of p is rows [p-w+1, p] inclusive → (len, w, 8)
        return np.stack([feat_std[p - w + 1: p + 1] for p in positions]).astype("float32")

    X_train, y_train = windows(train_pos), target[:n_train].astype("float32")
    X_val, y_val = windows(val_pos), target[n_train:].astype("float32")

    # Most recent window (as-of = last feature row, < reb_date) → r_hat input.
    X_pred = feat_std[n - w: n][None, :, :].astype("float32")

    return {
        "ticker": ticker,
        "X_train": X_train, "y_train": y_train,
        "X_val": X_val, "y_val": y_val,
        "X_pred": X_pred,
        "asof_pred_date": feats["date"].iloc[-1],
    }


# ─────────────────────────────────────────────────────────────────────────────
# LSTM feature extractor (Option A: linear head, train, then discard the head)
# ─────────────────────────────────────────────────────────────────────────────
def _build_lstm():
    torch = _torch()
    nn = torch.nn

    class IndicatorLSTM(nn.Module):
        """LSTM encoder + a linear head used ONLY during training (Option A).
        After training, call .encode(x) and ignore the head."""

        def __init__(self, input_size=C.N_FEATURES, hidden_size=C.LSTM_HIDDEN,
                     num_layers=C.LSTM_LAYERS):
            super().__init__()
            self.lstm = nn.LSTM(input_size, hidden_size, num_layers, batch_first=True)
            self.head = nn.Linear(hidden_size, 1)

        def encode(self, x):
            _, (h_n, _) = self.lstm(x)
            return h_n[-1]                               # (batch, hidden)

        def forward(self, x):
            return self.head(self.encode(x)).squeeze(-1)

    return IndicatorLSTM


def train_lstm(X_train, y_train, X_val, y_val, epochs: int, device=None, seed: int = 0):
    """Train the LSTM end-to-end (MSE) and return the trained module."""
    torch = _torch()
    torch.manual_seed(seed)
    device = device or get_device()

    Model = _build_lstm()
    model = Model().to(device)
    opt = torch.optim.Adam(model.parameters(), lr=C.LSTM_LR)
    loss_fn = torch.nn.MSELoss()

    Xt = torch.as_tensor(X_train, device=device)
    yt = torch.as_tensor(y_train, device=device)
    n = Xt.shape[0]
    bs = min(C.LSTM_BATCH, n)

    best_state, best_val = None, float("inf")
    Xv = torch.as_tensor(X_val, device=device)
    yv = torch.as_tensor(y_val, device=device)

    for _ in range(epochs):
        model.train()
        perm = torch.randperm(n, device=device)
        for i in range(0, n, bs):
            idx = perm[i:i + bs]
            opt.zero_grad()
            loss = loss_fn(model(Xt[idx]), yt[idx])
            loss.backward()
            opt.step()
        # cheap early-stopping bookkeeping on val MSE
        model.eval()
        with torch.no_grad():
            v = loss_fn(model(Xv), yv).item()
        if v < best_val:
            best_val, best_state = v, {k: t.detach().clone() for k, t in model.state_dict().items()}

    if best_state is not None:
        model.load_state_dict(best_state)
    return model


def _encode(model, X, device):
    torch = _torch()
    model.eval()
    with torch.no_grad():
        return model.encode(torch.as_tensor(X, device=device)).cpu().numpy()


# ─────────────────────────────────────────────────────────────────────────────
# Full per-stock train + predict
# ─────────────────────────────────────────────────────────────────────────────
def train_and_predict_at_date(ticker: str, reb_date, epochs: Optional[int] = None,
                              svr_C: float = C.SVR_C, svr_eps: float = C.SVR_EPSILON,
                              device=None) -> Optional[dict]:
    """Spec 03 §6 — the unit of work. Returns {'ticker', 'r_hat', 'omega'} or None."""
    from sklearn.svm import SVR

    data = build_training_data(ticker, reb_date)
    if data is None:
        return None
    epochs = epochs if epochs is not None else C.LSTM_EPOCHS
    device = device or get_device()

    try:
        model = train_lstm(data["X_train"], data["y_train"],
                            data["X_val"], data["y_val"], epochs=epochs, device=device)
        H_train = _encode(model, data["X_train"], device)
        H_val = _encode(model, data["X_val"], device)
        H_pred = _encode(model, data["X_pred"], device)
    except Exception as e:  # noqa: BLE001
        # re-raise OOM so M7's CPU fallback / caller can react; skip everything else
        if "out of memory" in str(e).lower():
            raise
        warnings.warn(f"[M3] {ticker} @ {reb_date}: LSTM failed: {e}")
        return None

    svr = SVR(kernel=C.SVR_KERNEL, C=svr_C, epsilon=svr_eps)
    svr.fit(H_train, data["y_train"])

    # ω_i — residual variance on the VALIDATION set only (03 §5)
    pred_val = svr.predict(H_val)
    omega_i = float(np.var(pred_val - data["y_val"]))

    r_hat = float(svr.predict(H_pred)[0])
    return {"ticker": ticker, "r_hat": r_hat, "omega": omega_i}


# ─────────────────────────────────────────────────────────────────────────────
# SVR hyperparameter tuning — once, on a sample, reused everywhere (09 §4)
# ─────────────────────────────────────────────────────────────────────────────
def tune_svr_hyperparams(sample_tickers: list[str], ref_date, epochs: int,
                         device=None) -> tuple[float, float]:
    """Grid-search (C, ε) once on a representative sample at one reference date,
    scoring by mean validation MSE. Returns the single (C, ε) applied to every
    stock and every rebalance (09 §4)."""
    from sklearn.svm import SVR
    device = device or get_device()

    encoded = []  # (H_train, y_train, H_val, y_val) per usable sample stock
    for t in sample_tickers:
        data = build_training_data(t, ref_date)
        if data is None:
            continue
        try:
            model = train_lstm(data["X_train"], data["y_train"],
                               data["X_val"], data["y_val"], epochs=epochs, device=device)
            encoded.append((_encode(model, data["X_train"], device), data["y_train"],
                            _encode(model, data["X_val"], device), data["y_val"]))
        except Exception as e:  # noqa: BLE001
            warnings.warn(f"[M3-tune] {t} skipped: {e}")

    if not encoded:
        warnings.warn("[M3-tune] no usable sample stocks — using placeholder (C, ε).")
        return C.SVR_C, C.SVR_EPSILON

    best, best_mse = (C.SVR_C, C.SVR_EPSILON), float("inf")
    for Cval in C.SVR_TUNE_GRID["C"]:
        for eps in C.SVR_TUNE_GRID["epsilon"]:
            mses = []
            for H_tr, y_tr, H_va, y_va in encoded:
                svr = SVR(kernel=C.SVR_KERNEL, C=Cval, epsilon=eps).fit(H_tr, y_tr)
                mses.append(float(np.mean((svr.predict(H_va) - y_va) ** 2)))
            mean_mse = float(np.mean(mses))
            if mean_mse < best_mse:
                best_mse, best = mean_mse, (Cval, eps)
    print(f"[M3-tune] selected C={best[0]}, epsilon={best[1]} "
          f"(mean val MSE {best_mse:.2e}, {len(encoded)} sample stocks).")
    return best


# ─────────────────────────────────────────────────────────────────────────────
# Batch predictions for one rebalance date (Module 3 → Module 4 contract)
# ─────────────────────────────────────────────────────────────────────────────
def predict_universe(tickers: list[str], reb_date, epochs: int,
                     svr_C: float, svr_eps: float, n_jobs: int = 1,
                     device=None, progress_every: int = 25) -> pd.DataFrame:
    """Run train_and_predict_at_date for every ticker → DataFrame[ticker, r_hat, omega].

    n_jobs > 1 fans out across stocks with joblib (independent per stock, 07 §5).
    Prints periodic per-stock progress so a long per-date training pass (hundreds
    of stocks) never looks hung.
    """
    n = len(tickers)
    key = pd.Timestamp(reb_date).date().isoformat()

    def one(t):
        try:
            return train_and_predict_at_date(t, reb_date, epochs=epochs,
                                             svr_C=svr_C, svr_eps=svr_eps, device=device)
        except Exception as e:  # noqa: BLE001
            warnings.warn(f"[M3] {t} @ {reb_date}: {e}")
            return None

    if n_jobs and n_jobs != 1:
        from joblib import Parallel, delayed
        # joblib's verbose emits periodic "Done X tasks | elapsed:" lines to stderr
        results = Parallel(n_jobs=n_jobs, prefer="processes", verbose=10)(
            delayed(one)(t) for t in tickers)
    else:
        results, skipped = [], 0
        for i, t in enumerate(tickers, 1):
            r = one(t)
            results.append(r)
            skipped += (r is None)
            if i % progress_every == 0 or i == n:
                print(f"      [M3] {key}: {i}/{n} stocks trained "
                      f"({skipped} skipped)", flush=True)

    rows = [r for r in results if r is not None]
    print(f"    [M3] {key}: {len(rows)}/{n} predictions ready "
          f"({n - len(rows)} skipped).", flush=True)
    return pd.DataFrame(rows, columns=["ticker", "r_hat", "omega"])
