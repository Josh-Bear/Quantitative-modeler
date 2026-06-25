"""
lstm_model.py — PyTorch 4-layer LSTM forecasting all 8 indicators HORIZON days ahead.

Architecture B (BL_LSTM_Implementation_Plan.md): ONE model per stock with an 8-wide
output head — it predicts every indicator at once, rather than 8 separate models. This
is the Keras stack ported to PyTorch:

    LSTM(8 → 60) × 4 layers, dropout 30% between layers, Dense(60 → 8) on the last
    timestep. Adam(lr=5e-3), MSE loss, batch 256. The training loop mirrors the plan's
    Keras callbacks: a progress logger, EarlyStopping (restore best weights) and
    ReduceLROnPlateau — all driven by the validation split.
"""
from __future__ import annotations

import copy

import numpy as np
import torch
from torch import nn
from torch.optim.lr_scheduler import ReduceLROnPlateau

from . import constants as C
from .preprocessing import StockData


def get_device(prefer: str = "auto") -> torch.device:
    """Resolve a torch device. prefer: 'auto' | 'cpu' | 'mps' | 'cuda'.
    Non-auto choices fall back to CPU if the requested backend is unavailable."""
    prefer = (prefer or "auto").lower()
    if prefer == "cpu":
        return torch.device("cpu")
    if prefer == "mps":
        return torch.device("mps") if torch.backends.mps.is_available() else torch.device("cpu")
    if prefer == "cuda":
        return torch.device("cuda") if torch.cuda.is_available() else torch.device("cpu")
    if torch.backends.mps.is_available():
        return torch.device("mps")
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def _empty_cache(device: torch.device) -> None:
    if device.type == "mps":
        torch.mps.empty_cache()
    elif device.type == "cuda":
        torch.cuda.empty_cache()


class LSTMRegressor(nn.Module):
    """4-layer LSTM with a multi-output Dense head (Architecture B)."""

    def __init__(self, n_features: int = C.LSTM_OUTPUTS, hidden: int = C.LSTM_HIDDEN,
                 layers: int = C.LSTM_LAYERS, dropout: float = C.LSTM_DROPOUT,
                 output_size: int = C.LSTM_OUTPUTS):
        super().__init__()
        self.lstm = nn.LSTM(
            input_size=n_features, hidden_size=hidden, num_layers=layers,
            batch_first=True, dropout=dropout if layers > 1 else 0.0,
        )
        self.head = nn.Linear(hidden, output_size)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out, _ = self.lstm(x)                 # (B, T, hidden)
        return self.head(out[:, -1, :])       # (B, output_size)


def _train_one(X, Y, Xval, Yval, *, epochs, lr, batch, device, ticker="",
               log_every=C.LOG_EVERY, patience=C.EARLY_STOP_PATIENCE):
    """Train one multi-output model with val-driven early stopping + LR plateau."""
    model = LSTMRegressor(n_features=X.shape[2], output_size=Y.shape[1]).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    sched = ReduceLROnPlateau(opt, factor=C.LR_PLATEAU_FACTOR, patience=C.LR_PLATEAU_PATIENCE)
    loss_fn = nn.MSELoss()

    Xt = torch.as_tensor(X, dtype=torch.float32, device=device)
    yt = torch.as_tensor(Y, dtype=torch.float32, device=device)
    n = Xt.shape[0]
    has_val = Xval is not None and len(Xval) > 0
    if has_val:
        Xvt = torch.as_tensor(Xval, dtype=torch.float32, device=device)
        yvt = torch.as_tensor(Yval, dtype=torch.float32, device=device)

    best_val, best_state, bad = float("inf"), None, 0
    for ep in range(1, epochs + 1):
        model.train()
        perm = torch.randperm(n, device=device)
        for s in range(0, n, batch):
            idx = perm[s:s + batch]
            opt.zero_grad()
            loss = loss_fn(model(Xt[idx]), yt[idx])
            loss.backward()
            opt.step()

        if has_val:
            model.eval()
            with torch.no_grad():
                vloss = float(loss_fn(model(Xvt), yvt).item())
            sched.step(vloss)
            if vloss < best_val - 1e-7:
                best_val, best_state, bad = vloss, copy.deepcopy(model.state_dict()), 0
            else:
                bad += 1
            if log_every and ep % log_every == 0:
                print(f"      [{ticker}] epoch {ep:>3} | train {float(loss):.4f} | val {vloss:.4f}")
            if bad >= patience:
                print(f"      [{ticker}] early stop at epoch {ep} (best val {best_val:.4f})")
                break
        elif log_every and ep % log_every == 0:
            print(f"      [{ticker}] epoch {ep:>3} | train {float(loss):.4f}")

    if best_state is not None:
        model.load_state_dict(best_state)

    model.eval()
    del Xt, yt, opt
    if has_val:
        del Xvt, yvt
    _empty_cache(device)
    return model, (best_val if best_val != float("inf") else float("nan"))


@torch.no_grad()
def predict_indicators(model: LSTMRegressor, X: np.ndarray) -> np.ndarray:
    """Predicted scaled indicators (len(X), 8). Runs on the model's current device."""
    dev = next(model.parameters()).device
    Xt = torch.as_tensor(X, dtype=torch.float32, device=dev)
    return model(Xt).detach().cpu().numpy()


def train_stock_model(sd: StockData, *, epochs: int = C.LSTM_EPOCHS, lr: float = C.LSTM_LR,
                      batch: int = C.LSTM_BATCH, device: torch.device | None = None,
                      seed: int = 42) -> dict:
    """Train the single multi-output LSTM for one stock and score it on the test split."""
    device = device or get_device()
    torch.manual_seed(seed)

    w = sd.windows
    tr, va, te = w["train"], w["val"], w["test"]
    Xtr, Ytr = w["X"][tr], w["Y"][tr]
    Xva, Yva = w["X"][va], w["Y"][va]
    Xte, Yte = w["X"][te], w["Y"][te]

    model, val_mse = _train_one(Xtr, Ytr, Xva, Yva, epochs=epochs, lr=lr,
                                batch=batch, device=device, ticker=sd.ticker)
    model.to("cpu")          # park on CPU to free GPU memory
    _empty_cache(device)

    test_pred = (predict_indicators(model, Xte)
                 if len(Xte) else np.empty((0, C.LSTM_OUTPUTS)))
    mse_test = (((test_pred - Yte) ** 2).mean(axis=0)
                if len(Xte) else np.full(C.LSTM_OUTPUTS, np.nan))

    return {
        "model": model,
        "device": device,
        "val_mse": val_mse,                   # best validation MSE (8-output, scaled)
        "mse_test": mse_test,                 # per-indicator test MSE (scaled space)
        "test_pred": test_pred,               # (n_test, 8) predicted indicators @ target day
        "test_asof_idx": w["asof_idx"][te],
        "test_target_idx": w["target_idx"][te],
        "test_asof_dates": w["asof_dates"][te],
        "test_target_dates": w["target_dates"][te],
    }
