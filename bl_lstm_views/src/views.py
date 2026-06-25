"""
views.py — turn per-stock LSTM+SVR forecasts into Black-Litterman views.

For each stock we:
  1. train the 8 LSTM indicator models and the SVR price decoder,
  2. forecast HORIZON days ahead from the latest window → predicted price,
  3. form the view return  q = (pred_price − last_close) / last_close   (summary eq. 8),
  4. set the view's uncertainty Ω from the model's realised test error
     (low error → small Ω → BL trusts the view more; summary §6.4).

Units: the prior Π and covariance Σ are annualised, so view returns are annualised
linearly (factor TRADING_DAYS / HORIZON) to live in the same space; Ω (a variance) is
scaled by that factor squared. This linear annualisation is an intentional, documented
simplification — see README.

Views are absolute (one per stock), so the pick matrix P is the identity.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import numpy as np

from . import constants as C
from .lstm_model import get_device, predict_indicators, train_stock_model
from .preprocessing import StockData
from .svr_model import predict_price, train_close_svr, train_fit_mse

ANN = C.TRADING_DAYS / C.HORIZON          # linear annualisation factor for HORIZON returns
OMEGA_FLOOR = 1e-6                         # keep Ω strictly positive (invertible)


def _latest_window(sd: StockData) -> np.ndarray:
    """The most recent TIME_WINDOW of scaled features → (1, window, 8) for a live forecast."""
    w = sd.feats_scaled[-C.TIME_WINDOW:]
    return w[None, :, :].astype(np.float32)


def compose_view(sd: StockData, lstm: dict, svr) -> dict:
    """Turn an already-trained LSTM result + SVR into one stock's view dict.

    Single source of truth for the Q/Ω math — reused by both generate_views()
    (which trains first) and the notebook (which trains in its own cells)."""
    cap = C.VIEW_Q_CAP

    # ── live forecast (as of the last available day) ─────────────────────────
    pred_ind_live = predict_indicators(lstm["model"], _latest_window(sd))  # (1,8)
    pred_price_live = float(predict_price(svr, sd, pred_ind_live, sd.ref_raw[-1])[0])
    last_close = float(sd.close_raw[-1])
    q_raw = (pred_price_live - last_close) / last_close
    q_horizon = float(np.clip(q_raw, -cap, cap))     # capQ discipline (BugFix #3)
    q_annual = q_horizon * ANN

    # ── Ω from realised test error of the (clamped) *view return* ────────────
    if lstm["test_pred"].shape[0] > 0:
        ref_asof = sd.ref_raw[lstm["test_asof_idx"]]
        pred_price_test = predict_price(svr, sd, lstm["test_pred"], ref_asof)
        close_asof = sd.close_raw[lstm["test_asof_idx"]]
        actual_price = sd.close_raw[lstm["test_target_idx"]]
        pred_ret = np.clip((pred_price_test - close_asof) / close_asof, -cap, cap)
        actual_ret = (actual_price - close_asof) / close_asof
        view_mse_horizon = float(np.mean((pred_ret - actual_ret) ** 2))
    else:
        view_mse_horizon = float(np.nanmean(lstm["mse_test"]))  # fallback proxy

    omega = max(view_mse_horizon * (ANN ** 2) * C.OMEGA_SCALE, OMEGA_FLOOR)

    return {
        "ticker": sd.ticker,
        "q_horizon": q_horizon,
        "q_annual": q_annual,
        "omega": omega,
        "pred_price": pred_price_live,
        "last_close": last_close,
        "lstm_val_mse": float(lstm["val_mse"]),
        "lstm_mse_mean": float(np.nanmean(lstm["mse_test"])),
        "svr_fit_mse": train_fit_mse(svr, sd),
        "view_mse_horizon": view_mse_horizon,
        # handles reused by the backtest (avoid retraining)
        "_model": lstm["model"],
        "_svr": svr,
        "_lstm": lstm,
    }


def _stock_view(sd: StockData, epochs: int, device) -> dict:
    """Train one stock (LSTM + SVR) and compose its view."""
    lstm = train_stock_model(sd, epochs=epochs, device=device)
    svr = train_close_svr(sd)
    return compose_view(sd, lstm, svr)


def assemble_package(per_stock: dict) -> dict:
    """Build the BL view package {asOf, tickers, P, Q, omega, per_stock} from
    per-stock view dicts (keyed by ticker)."""
    tickers = list(per_stock.keys())
    Q = np.array([per_stock[t]["q_annual"] for t in tickers])
    omega = np.array([per_stock[t]["omega"] for t in tickers])
    return {
        "asOf": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "tickers": tickers,
        "P": np.eye(len(tickers)),          # absolute views
        "Q": Q, "omega": omega,
        "per_stock": per_stock,
    }


def generate_views(stock_data: dict[str, StockData], *, epochs: int = C.LSTM_EPOCHS,
                   device=None) -> dict:
    """Train every stock (one multi-output LSTM + SVR each) and assemble the package.

    A stock that fails to train (bad/incomplete data, SVR fit error, …) is skipped
    and the run continues with the rest. Out-of-memory is re-raised so the caller can
    fall back to CPU (see run.py) instead of silently dropping the whole universe."""
    device = device or get_device()
    per_stock = {}
    for t in stock_data:
        print(f"   ▸ {t}: training LSTM (8-output) + SVR ...")
        try:
            per_stock[t] = _stock_view(stock_data[t], epochs, device)
        except RuntimeError as e:
            if "out of memory" in str(e).lower():
                raise                      # let run.py retry the whole run on CPU
            print(f"   ⚠️  {t}: skipped ({e})")
        except Exception as e:
            print(f"   ⚠️  {t}: skipped ({e})")
    return assemble_package(per_stock)


def write_views_json(views: dict, path: str = C.VIEWS_JSON) -> None:
    """Serialise in the shape the JS engine's BL.compute() consumes (annualised returns)."""
    payload = {
        "asOf": views["asOf"],
        "horizonDays": C.HORIZON,
        "annualised": True,
        "tickers": views["tickers"],
        "P": np.asarray(views["P"]).tolist(),
        "Q": np.asarray(views["Q"]).tolist(),
        "omega": np.asarray(views["omega"]).tolist(),
        "diagnostics": {
            t: {k: views["per_stock"][t][k] for k in (
                "q_horizon", "q_annual", "omega", "pred_price", "last_close",
                "lstm_val_mse", "lstm_mse_mean", "svr_fit_mse", "view_mse_horizon")}
            for t in views["tickers"]
        },
    }
    with open(path, "w") as f:
        json.dump(payload, f, indent=2)
