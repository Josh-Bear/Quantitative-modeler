"""
ml_views.py — LSTM+SVR machine-generated views for the BL optimizer
(implements docs/ML_VIEWS_DESIGN.md)

Pipeline per stock (Architecture A — LSTM as feature extractor):
    daily OHLCV (2y) → 8 indicators → 30-day windows
    → LSTM(8→hidden) trained end-to-end on 63-day forward return (linear head)
    → discard head, hidden state → SVR(rbf) → r̂ (predicted 63-day return)
    → ω = variance of SVR residuals on the chronological validation slice

Then build_views() assembles:
    P  — absolute one-hot per stock + relative (top vs 2nd per sector)
    Q  — r̂ (absolute) / r̂ spread (relative)
    Ω  — 3 modes: he-litterman (P τΣ Pᵀ), svr-residual (calibrated), blend (50/50)

Does NOT touch the JS BL engine — output is consumed by app.js parseMLViews()
and pushed into state.views like any manually-entered view.

Indicator math mirrors bl_model_port_optimization/src/features.py (hand-rolled,
pure pandas/numpy). HT_DCPERIOD uses TA-Lib when available, else 0.0 + warning
(per design §2.1.1 — a missing TA-Lib must not crash the web server).
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

import ml_constants as C

# ── aliases so the rest of the file stays readable ───────────────────
WINDOW      = C.WINDOW
HORIZON     = C.HORIZON
WARMUP_DROP = C.WARMUP_DROP
MIN_ROWS    = C.MIN_ROWS
OMEGA_FLOOR = C.OMEGA_FLOOR

try:
    import talib
    _HAS_TALIB = True
except ImportError:
    _HAS_TALIB = False


# ── Progress tracking (single-user app → one module-level counter is enough) ─
# generate_ml_views() runs on a worker thread (see routers/ml_views.py); the
# request thread polls get_progress() via GET /api/ml-views/progress so the
# UI can show "Finished k/n" instead of a static spinner.
_progress = {"completed": 0, "total": 0}


def get_progress() -> dict:
    return dict(_progress)


# ═════════════════════════════════════════════════════════════════════
# 1. fetch_features — daily OHLCV → 8 indicators per ticker
# ═════════════════════════════════════════════════════════════════════
def _true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    return pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)


def _atr(high, low, close, window: int) -> pd.Series:
    return _true_range(high, low, close).rolling(window).mean()


def _rsi(close: pd.Series, window: int = 14) -> pd.Series:
    """Wilder's RSI: RS = avg_gain/avg_loss with Wilder smoothing."""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    avg_loss = loss.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    rs = avg_gain / avg_loss
    return 100 - 100 / (1 + rs)


def _macd_hist(close: pd.Series, fast=12, slow=26, signal=9) -> pd.Series:
    macd_line = close.ewm(span=fast, adjust=False).mean() - close.ewm(span=slow, adjust=False).mean()
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return macd_line - signal_line


def compute_indicators(hist: pd.DataFrame) -> pd.DataFrame:
    """One ticker's daily OHLCV (yfinance columns) → 8-indicator frame.

    Columns: rsi, atr, macd_hist, keltner_pos, bb_pctb, squeeze_on,
             momentum_pct, ht_dcperiod — warm-up rows dropped.
    Math mirrors bl_model_port_optimization/src/features.py so the two
    models stay comparable.
    """
    high, low, close = hist["High"], hist["Low"], hist["Close"]
    out = pd.DataFrame(index=hist.index)

    out["rsi"] = _rsi(close, window=14)
    out["atr"] = _atr(high, low, close, window=14)
    out["macd_hist"] = _macd_hist(close)

    # Keltner channel position — mid = EMA(20), bands = mid ± 2·ATR(10)
    kc_mid = close.ewm(span=20, adjust=False).mean()
    kc_atr = _atr(high, low, close, window=10)
    kc_upper = kc_mid + 2 * kc_atr
    kc_lower = kc_mid - 2 * kc_atr
    out["keltner_pos"] = (close - kc_lower) / (kc_upper - kc_lower)

    # Bollinger %B — mid = SMA(20), bands = mid ± 2·std(20)
    bb_mid = close.rolling(20).mean()
    bb_std = close.rolling(20).std()
    bb_upper = bb_mid + 2 * bb_std
    bb_lower = bb_mid - 2 * bb_std
    out["bb_pctb"] = (close - bb_lower) / (bb_upper - bb_lower)

    # TTM squeeze on/off — BB inside KC ⇒ compression
    out["squeeze_on"] = ((bb_upper < kc_upper) & (bb_lower > kc_lower)).astype(float)

    # 10-day rate of change
    out["momentum_pct"] = close.pct_change(periods=10)

    # Hilbert dominant cycle period — TA-Lib only; 0.0 fallback per design
    if _HAS_TALIB:
        out["ht_dcperiod"] = talib.HT_DCPERIOD(close.to_numpy(dtype="float64"))
    else:
        out["ht_dcperiod"] = 0.0

    out = out.iloc[WARMUP_DROP:]
    out = out.replace([np.inf, -np.inf], np.nan).dropna()
    return out


def fetch_features(tickers: list[str], period: str = C.FETCH_PERIOD) -> dict:
    """Fetch daily OHLCV via yfinance and compute the 8 indicators per ticker.

    Returns { TICKER: {features, close, sector}, ..., "errors": {TICKER: reason} }
    Failed tickers are skipped (recorded in errors) — the run continues.
    """
    import yfinance as yf

    if not _HAS_TALIB:
        warnings.warn("TA-Lib not installed — ht_dcperiod will be 0.0 for all tickers")

    out: dict = {"errors": {}}
    for ticker in tickers:
        t = ticker.strip().upper()
        if not t:
            continue
        try:
            yt = yf.Ticker(t)
            hist = yt.history(period=period, interval="1d", auto_adjust=True)
            if hist is None or hist.empty:
                out["errors"][t] = "no price history"
                continue

            feats = compute_indicators(hist)
            if len(feats) < MIN_ROWS:
                out["errors"][t] = f"only {len(feats)} rows after warm-up (need ≥{MIN_ROWS})"
                continue

            close = hist["Close"].reindex(feats.index)

            sector = "Unknown"
            try:
                sector = (yt.info or {}).get("sector") or "Unknown"
            except Exception:
                pass

            out[t] = {"features": feats, "close": close, "sector": sector}
            print(f"  ✅ {t}: {len(feats)} rows, sector={sector}")
        except Exception as e:  # noqa: BLE001
            out["errors"][t] = str(e)
            print(f"  ❌ {t}: {e}")
    return out


# ═════════════════════════════════════════════════════════════════════
# 2. train_lstm_svr — Architecture A: LSTM encoder → SVR → r̂, ω
# ═════════════════════════════════════════════════════════════════════
def train_lstm_svr(ticker: str, data: dict, epochs: int = C.LSTM_EPOCHS,
                   val_fraction: float = C.VAL_FRACTION,
                   hidden: int = C.LSTM_HIDDEN, n_layers: int = C.LSTM_LAYERS) -> dict:
    """Train one stock's LSTM encoder + SVR head; return r̂ (63-day) and ω.

    All exceptions are caught → success=False (never crash the server).
    """
    fail = lambda msg: {"ticker": ticker, "r_hat": 0.0, "omega": 0.0,  # noqa: E731
                        "sector": data.get("sector", "Unknown"),
                        "success": False, "error": msg}
    try:
        import torch
        import torch.nn as nn
        from sklearn.preprocessing import StandardScaler
        from sklearn.svm import SVR
    except ImportError as e:
        return fail(f"missing dependency: {e}")

    try:
        feats_df: pd.DataFrame = data["features"]
        close: pd.Series = data["close"]
        feats = feats_df.to_numpy(dtype=np.float64)
        n = len(feats)
        if n < MIN_ROWS:
            return fail(f"only {n} rows after warm-up (need ≥{MIN_ROWS})")

        # 63-day forward return target: y(t) = close[t+63]/close[t] - 1
        c = close.to_numpy(dtype=np.float64)
        y_full = np.full(n, np.nan)
        y_full[:n - HORIZON] = c[HORIZON:] / c[:n - HORIZON] - 1.0

        # sample as-of indices: need a full 30-day window AND a forward close
        asof = [i for i in range(WINDOW - 1, n) if np.isfinite(y_full[i])]
        n_samples = len(asof)
        n_train = int(n_samples * (1 - val_fraction))
        if n_train < C.MIN_TRAIN or n_samples - n_train < C.MIN_VAL:
            return fail(f"insufficient samples ({n_samples}) for train/val split")

        # StandardScaler fit on the TRAIN slice only (chronological — no shuffle)
        train_last_row = asof[n_train - 1]
        scaler = StandardScaler().fit(feats[:train_last_row + 1])
        feats_s = scaler.transform(feats)

        X = np.stack([feats_s[i - WINDOW + 1: i + 1] for i in asof]).astype(np.float32)
        y = np.array([y_full[i] for i in asof], dtype=np.float32)
        X_train, y_train = X[:n_train], y[:n_train]
        X_val, y_val = X[n_train:], y[n_train:]

        # Winsorize the TRAIN target only (per-stock, train-slice percentiles → no
        # leakage) so LSTM+SVR never learn to emit ±100% predictions. y_val stays
        # raw → ω / test MSE below measure honest error against real returns.
        y_train_fit = y_train
        if C.WINSOR_ENABLED and len(y_train) > 0:
            lo, hi = np.percentile(y_train, [100 * C.WINSOR_PCT, 100 * (1 - C.WINSOR_PCT)])
            y_train_fit = np.clip(y_train, lo, hi).astype(np.float32)

        # ── LSTM encoder + linear head, trained end-to-end on MSE ──────
        torch.manual_seed(42)
        device = torch.device("cpu")   # small model — CPU is fast + thread-safe
        lstm = nn.LSTM(input_size=feats.shape[1], hidden_size=hidden,
                       num_layers=n_layers, batch_first=True,
                       dropout=C.LSTM_DROPOUT if n_layers > 1 else 0.0).to(device)
        head = nn.Linear(hidden, 1).to(device)
        params = list(lstm.parameters()) + list(head.parameters())
        opt = torch.optim.Adam(params, lr=C.LSTM_LR)
        loss_fn = nn.MSELoss()

        Xt = torch.from_numpy(X_train).to(device)
        yt = torch.from_numpy(y_train_fit).unsqueeze(1).to(device)
        Xv = torch.from_numpy(X_val).to(device)
        yv = torch.from_numpy(y_val).unsqueeze(1).to(device)

        def encode(x: "torch.Tensor") -> "torch.Tensor":
            _, (h_n, _) = lstm(x)
            return h_n[-1]                     # (batch, hidden)

        best_val, best_state, bad = np.inf, None, 0
        batch = C.LSTM_BATCH
        for _ in range(epochs):
            lstm.train(); head.train()
            perm = torch.arange(len(Xt))       # chronological — no shuffle
            for s in range(0, len(Xt), batch):
                idx = perm[s:s + batch]
                opt.zero_grad()
                pred = head(encode(Xt[idx]))
                loss = loss_fn(pred, yt[idx])
                loss.backward()
                opt.step()

            lstm.eval(); head.eval()
            with torch.no_grad():
                val_mse = loss_fn(head(encode(Xv)), yv).item()
            if val_mse < best_val - 1e-8:
                best_val, bad = val_mse, 0
                best_state = {k: v.detach().clone() for k, v in lstm.state_dict().items()}
            else:
                bad += 1
                if bad >= C.LSTM_PATIENCE:
                    break

        if best_state is not None:
            lstm.load_state_dict(best_state)   # restore best encoder, discard head
        lstm.eval()

        # ── hidden states → SVR ────────────────────────────────────────
        with torch.no_grad():
            H_train = encode(Xt).cpu().numpy()
            H_val = encode(Xv).cpu().numpy()

        svr = SVR(kernel=C.SVR_KERNEL, C=C.SVR_C, epsilon=C.SVR_EPSILON)
        svr.fit(H_train, y_train_fit)

        # ω = residual variance on the VALIDATION slice only (design §2.1.2 step 7).
        # y_val is RAW (un-winsorized) → ω reflects true error on real returns, so a
        # stock with genuinely wild returns correctly gets a large ω (BL distrusts it).
        residuals = svr.predict(H_val) - y_val
        omega = float(np.var(residuals))
        if omega <= 0:
            omega = OMEGA_FLOOR

        # Per-stock diagnostics for the "ML Model" page: LSTM best val MSE,
        # SVR fit on train vs held-out val (= this pipeline's test slice).
        # Train MSE is measured against the winsorized target the SVR actually fit.
        svr_train_mse = float(np.mean((svr.predict(H_train) - y_train_fit) ** 2))
        svr_test_mse = float(np.mean(residuals ** 2))

        # r̂ from the most recent 30-day window
        X_pred = feats_s[-WINDOW:][None].astype(np.float32)
        with torch.no_grad():
            H_pred = encode(torch.from_numpy(X_pred).to(device)).cpu().numpy()
        r_hat = float(svr.predict(H_pred)[0])

        return {"ticker": ticker, "r_hat": r_hat, "omega": omega,
                "sector": data.get("sector", "Unknown"),
                "n_rows": int(n), "n_train": int(n_train),
                "n_val": int(n_samples - n_train),
                "lstm_val_mse": float(best_val),
                "svr_train_mse": svr_train_mse,
                "svr_test_mse": svr_test_mse,
                "success": True, "error": None}
    except Exception as e:  # noqa: BLE001
        return fail(str(e))


# ═════════════════════════════════════════════════════════════════════
# 3. build_views — P, Q, Ω (3 modes)
# ═════════════════════════════════════════════════════════════════════
def build_views(results: list[dict], sigma: np.ndarray, tau: float = 0.05) -> dict:
    """Assemble P, Q and the three Ω modes from per-stock (r̂, ω, sector).

    `results` and `sigma` MUST share the same ordering: alphabetical by
    sector then ticker (generate_ml_views guarantees this).
    """
    n = len(results)
    stock_order = [r["ticker"] for r in results]
    sectors = {r["ticker"]: r["sector"] for r in results}

    # ── Cross-sectional shrinkage on raw r̂ (before annualisation) ──────
    # Bayesian precision weight β_i = Var_cs(r̂) / (Var_cs(r̂) + λ·test_MSE_i):
    # stocks whose SVR generalises poorly (high test MSE) are pulled toward
    # SHRINK_TARGET; well-fit stocks are kept. Pools info across stocks — which
    # BL's per-view Ω cannot do. β can reorder stocks (a poorly-fit high-r̂ name is
    # intentionally out-ranked by a well-fit lower-r̂ one).
    raw_rhat = np.array([r["r_hat"] for r in results], dtype=float)
    if C.SHRINK_ENABLED and n > 1:
        mse = np.array([(r.get("svr_test_mse") or 0.0) for r in results], dtype=float)
        var_cs = float(np.var(raw_rhat))
        denom = var_cs + C.SHRINK_STRENGTH * mse
        beta = np.where(denom > 0, var_cs / denom, 1.0)
        shrunk_rhat = C.SHRINK_TARGET + beta * (raw_rhat - C.SHRINK_TARGET)
    else:
        beta = np.ones(n)
        shrunk_rhat = raw_rhat

    # Annualise the SHRUNK r̂ and ω using C.ANNUALISE = 252/HORIZON (≈ 4).
    # SVR output is a 63-day return; JS BL engine uses annualised Σ.
    r_hat = shrunk_rhat * C.ANNUALISE
    omega_ml = np.array([r["omega"] for r in results]) * (C.ANNUALISE ** 2)

    # per-stock shrink audit for the diagnostics table (raw vs shrunk, β)
    shrink = {stock_order[i]: {"raw": float(raw_rhat[i]),
                               "shrunk": float(shrunk_rhat[i]),
                               "beta": float(beta[i])} for i in range(n)}

    tau_sigma = tau * sigma

    # ── Absolute views: one-hot per stock ─────────────────────────────
    P_rows = [np.eye(n)[i] for i in range(n)]
    Q_vals = list(r_hat)
    raw_omega = list(omega_ml)          # svr-residual raw values (absolute)
    n_absolute = n

    # ── Relative views: top vs 2nd by r̂ within each sector (≥2 stocks) ─
    by_sector: dict[str, list[int]] = {}
    for i, r in enumerate(results):
        by_sector.setdefault(r["sector"], []).append(i)

    n_relative = 0
    for sec in sorted(by_sector):
        idxs = by_sector[sec]
        if len(idxs) < 2:
            continue                     # 1 stock → absolute view only
        ranked = sorted(idxs, key=lambda i: r_hat[i], reverse=True)
        top, second = ranked[0], ranked[1]
        row = np.zeros(n)
        row[top], row[second] = 1.0, -1.0
        P_rows.append(row)
        Q_vals.append(float(r_hat[top] - r_hat[second]))
        raw_omega.append(float(omega_ml[top] + omega_ml[second]))  # sum of both errors
        n_relative += 1

    P = np.stack(P_rows)                                   # (K, N)
    Q = np.array(Q_vals)                                   # (K,)
    raw = np.array(raw_omega)
    K = len(Q)

    # ── Mode 1: he-litterman — Ω_k = P_k τΣ P_kᵀ ─────────────────────
    hl = np.array([float(P[k] @ tau_sigma @ P[k]) for k in range(K)])

    # ── Mode 2: svr-residual — calibrated with SEPARATE abs/rel scales ─
    # (mirrors bl_model_port_optimization/05_BL_MODEL §5)
    abs_mask = np.zeros(K, dtype=bool); abs_mask[:n_absolute] = True
    rel_mask = ~abs_mask

    med_abs_raw = np.median(raw[abs_mask]) if abs_mask.any() else 0.0
    alpha_abs = (np.median(np.diag(tau_sigma)) / med_abs_raw) if med_abs_raw > 0 else 1.0

    if rel_mask.any():
        rel_implied = np.array([float(P[k] @ tau_sigma @ P[k])
                                for k in range(K) if rel_mask[k]])
        med_rel_raw = np.median(raw[rel_mask])
        alpha_rel = (np.median(rel_implied) / med_rel_raw) if med_rel_raw > 0 else 1.0
    else:
        alpha_rel = 1.0

    svr_cal = raw.copy()
    svr_cal[abs_mask] *= alpha_abs
    svr_cal[rel_mask] *= alpha_rel

    # ── Mode 3: blend — 50/50 market structure vs model error ─────────
    blend = 0.5 * hl + 0.5 * svr_cal

    # Ω floor so no mode can hand the engine a singular diagonal (design §6)
    hl = np.maximum(hl, OMEGA_FLOOR)
    svr_cal = np.maximum(svr_cal, OMEGA_FLOOR)
    blend = np.maximum(blend, OMEGA_FLOOR)

    return {
        "stock_order": stock_order,
        "P": P.tolist(),
        "Q": Q.tolist(),
        "omega": {
            "he-litterman": hl.tolist(),
            "svr-residual": svr_cal.tolist(),
            "blend": blend.tolist(),
        },
        "n_absolute": n_absolute,
        "n_relative": n_relative,
        "sectors": sectors,
        "shrink": shrink,
    }


# ═════════════════════════════════════════════════════════════════════
# 4. generate_ml_views — main entry point (called from the router)
# ═════════════════════════════════════════════════════════════════════
def generate_ml_views(tickers: list[str], tau: float = C.BL_TAU,
                      delta: float = C.BL_DELTA, epochs: int = C.LSTM_EPOCHS) -> dict:
    """fetch → train per ticker (sequential) → Σ → build_views → JSON payload."""
    data = fetch_features(tickers)
    errors: dict[str, str] = dict(data.pop("errors"))

    # Per-stock diagnostics (ML Model page): fetch rows + train/val MSEs
    diagnostics = [{"ticker": t, "n_rows": 0, "success": False, "error": reason}
                   for t, reason in sorted(errors.items())]

    _progress["completed"] = 0
    _progress["total"] = len(data)

    results = []
    for t in sorted(data):
        print(f"  🧠 {t}: training LSTM+SVR (epochs={epochs}) ...")
        res = train_lstm_svr(t, data[t], epochs=epochs)
        _progress["completed"] += 1
        if res["success"]:
            results.append(res)
            diagnostics.append({k: res[k] for k in (
                "ticker", "sector", "n_rows", "n_train", "n_val",
                "lstm_val_mse", "svr_train_mse", "svr_test_mse",
                "r_hat", "omega", "success")})
            print(f"     r̂={res['r_hat']:+.4f}  ω={res['omega']:.6f}")
        else:
            errors[t] = res["error"]
            diagnostics.append({"ticker": t, "sector": data[t].get("sector", "Unknown"),
                                "n_rows": len(data[t]["features"]),
                                "success": False, "error": res["error"]})
            print(f"  ⚠️  {t}: skipped ({res['error']})")

    if not results:
        return {"ok": False, "error": "no stocks trained successfully",
                "errors": errors, "diagnostics": diagnostics}

    # Fixed ordering: alphabetical by sector, then ticker (design §2.1.3)
    results.sort(key=lambda r: (r["sector"], r["ticker"]))
    order = [r["ticker"] for r in results]

    # Σ from aligned daily returns of successful tickers, annualised ×252
    closes = pd.DataFrame({t: data[t]["close"] for t in order}).dropna()
    returns = closes.pct_change().dropna()
    sigma = returns.cov().values * 252

    views = build_views(results, sigma, tau=tau)
    shrink = views.get("shrink", {})

    # Augment each successful ticker's diagnostics with the pre-shrink raw r̂ and its
    # shrink β (rendered as extra columns on the Model Diagnostics table).
    for d in diagnostics:
        info = shrink.get(d.get("ticker"))
        if d.get("success") and info:
            d["r_hat_raw"] = info["raw"]
            d["shrink_beta"] = info["beta"]

    return {
        "ok": True,
        **views,
        # r_hats = post-shrink (feeds the bar chart + ML Views r̂ column, consistent
        # with the shrunk Q). Pre-shrink values live in diagnostics[].r_hat_raw.
        "r_hats": {t: info["shrunk"] for t, info in shrink.items()},
        "errors": errors,
        "diagnostics": diagnostics,
    }
