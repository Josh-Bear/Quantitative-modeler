"""
lstm_model.py — PyTorch 4-layer LSTM that forecasts each indicator HORIZON days ahead.

One model per indicator (8 per stock), per BL_LSTM_Project_Summary.md §4.1:
    LSTM(8 → 60) × 4 layers, dropout 30% between layers, Linear(60 → 1) on the last
    timestep. Adam(lr=5e-3), MSE loss, batch 256. PyTorch applies inter-layer dropout
    after layers 1–3 (not the last), which matches the summary's diagram exactly.
"""
from __future__ import annotations

import numpy as np
import torch
from torch import nn

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
    def __init__(self, n_features: int = 8, hidden: int = C.LSTM_HIDDEN,
                 layers: int = C.LSTM_LAYERS, dropout: float = C.LSTM_DROPOUT):
        super().__init__()
        self.lstm = nn.LSTM(
            input_size=n_features, hidden_size=hidden, num_layers=layers,
            batch_first=True, dropout=dropout if layers > 1 else 0.0,
        )
        self.head = nn.Linear(hidden, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out, _ = self.lstm(x)            # (B, T, hidden)
        return self.head(out[:, -1, :]).squeeze(-1)   # (B,)


def _train_one(X: np.ndarray, y: np.ndarray, *, epochs: int, lr: float,
               batch: int, device: torch.device) -> LSTMRegressor:
    model = LSTMRegressor(n_features=X.shape[2]).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    loss_fn = nn.MSELoss()

    Xt = torch.as_tensor(X, dtype=torch.float32, device=device)
    yt = torch.as_tensor(y, dtype=torch.float32, device=device)
    n = Xt.shape[0]

    model.train()
    for _ in range(epochs):
        perm = torch.randperm(n, device=device)
        for s in range(0, n, batch):
            idx = perm[s:s + batch]
            opt.zero_grad()
            loss = loss_fn(model(Xt[idx]), yt[idx])
            loss.backward()
            opt.step()

    model.eval()
    del Xt, yt, opt           # release the training tensors before the next model
    _empty_cache(device)
    return model


@torch.no_grad()
def predict_indicators(models: list[LSTMRegressor], X: np.ndarray) -> np.ndarray:
    """Predicted scaled indicators (len(X), 8) — column k from model k.
    Runs on whatever device the models currently sit on (CPU after training)."""
    dev = next(models[0].parameters()).device
    Xt = torch.as_tensor(X, dtype=torch.float32, device=dev)
    cols = [m(Xt).detach().cpu().numpy() for m in models]
    return np.stack(cols, axis=1)


def train_all_indicators(sd: StockData, *, epochs: int = C.LSTM_EPOCHS,
                         lr: float = C.LSTM_LR, batch: int = C.LSTM_BATCH,
                         device: torch.device | None = None, seed: int = 42) -> dict:
    """Train all 8 indicator models for one stock and score them on the test split."""
    device = device or get_device()
    torch.manual_seed(seed)

    w = sd.windows
    tr, te = w["train"], w["test"]
    Xtr, Ytr = w["X"][tr], w["Y"][tr]
    Xte, Yte = w["X"][te], w["Y"][te]

    models: list[LSTMRegressor] = []
    for k, name in enumerate(C.FEATURES):
        m = _train_one(Xtr, Ytr[:, k], epochs=epochs, lr=lr, batch=batch, device=device)
        m.to("cpu")               # park trained models on CPU to free GPU memory
        models.append(m)
        _empty_cache(device)
        print(f"      • {sd.ticker} LSTM[{name}] trained "
              f"({len(Xtr)} samples, {epochs} epochs)")

    test_pred = (predict_indicators(models, Xte)
                 if len(Xte) else np.empty((0, len(C.FEATURES))))
    mse_test = (((test_pred - Yte) ** 2).mean(axis=0)
                if len(Xte) else np.full(len(C.FEATURES), np.nan))

    return {
        "models": models,
        "device": device,
        "mse_test": mse_test,                 # per-indicator MSE (scaled space)
        "test_pred": test_pred,               # (n_test, 8) predicted indicators @ target day
        "test_asof_idx": w["asof_idx"][te],
        "test_target_idx": w["target_idx"][te],
        "test_asof_dates": w["asof_dates"][te],
        "test_target_dates": w["target_dates"][te],
    }
