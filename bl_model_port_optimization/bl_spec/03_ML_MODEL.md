# Module 3: ML Model (LSTM → SVR, per stock)

**Depends on:** Module 2 (standardized indicator features)
**Produces output for:** Module 4 (Stock Selection), Module 5 (BL Model — needs Q and ω)

---

## 1. Goal

For each stock in the S&P 500 universe, train a model that takes the past 63 days of 8 indicators and predicts the **63-trading-day forward return**. This must be retrained at every rebalance date using a rolling 10-year window (walk-forward), not trained once.

This module also produces **ωᵢ**, the per-stock residual variance, used later to build the Ω (Omega) uncertainty matrix in Module 5.

---

## 2. Why the Input Window Is 63 Days, Not Shorter

The LSTM input window is set to **63 trading days — exactly matching the 63-day prediction horizon** (Section 3), rather than the shorter 30-day window used in early prototypes. This is a deliberate, locked design choice (`00_OVERVIEW.md` §4).

The reasoning:

1. **Horizon/look-back symmetry.** The model forecasts the return over the *next* 63 trading days, so it should be conditioned on at least the *previous* 63 trading days of indicator dynamics. A 30-day window shows the LSTM only ~half a horizon of context, forcing it to predict a quarter-ahead move from less than a quarter of history. Setting window = horizon (≈ one quarter ≈ one rebalance interval) gives every forecast a full horizon of context.

2. **Indicator memory.** Several of the 8 indicators have lookbacks of 14–26 bars (RSI 14, MACD 26+9, Bollinger/Keltner 20, Hilbert dominant cycle ~20–40). A 30-day window barely contains one full cycle of the slower indicators; 63 days lets the LSTM observe at least two full cycles, so it can learn how an indicator's *trajectory* — not just its latest level — relates to forward returns.

3. **Cadence alignment.** 63 trading days ≈ 3 calendar months = the quarterly rebalance interval (Module 7) and the forward-return target. Window, target, and rebalance frequency are all on the same ~quarter timescale, keeping the model's notion of "recent" consistent end to end.

**Cost of the change.** A longer window consumes more of each rolling 10-year slice as look-back (the first 62 rows can't form a full window, vs. the first 29 before), trimming ~33 training samples per stock per rebalance — negligible against the ~2,400 overlapping samples available (Section 3). It also doubles the LSTM's sequence length, modestly increasing per-stock training time, which is acceptable given Module 7's caching/parallelization. This 63-day window supersedes the earlier 30-day prototype window.

---

## 3. Target Variable Definition

```
target(t) = (close(t + 63) / close(t)) - 1
```

This is computed with **overlapping windows** (stride = 1 day) to maximize the number of training samples, since a 10-year rolling window only gives ~2520 trading days, and non-overlapping 63-day windows would give only ~40 samples per stock — far too few.

**Important consequence of overlap:** consecutive target values are highly autocorrelated (adjacent 63-day windows share 62 of 63 days). This is expected and acceptable for training, but:
- Train/validation split must still be **chronological** (e.g., last 20% of the time range by date, not random rows) to avoid leaking near-duplicate windows across the split.
- When computing ωᵢ (residual variance) in Section 6, be aware that the effective sample size is much smaller than the raw row count due to this autocorrelation. Report this caveat in the final write-up.

---

## 4. Model Architecture

### 4.1 LSTM stage

```python
import torch
import torch.nn as nn

class IndicatorLSTM(nn.Module):
    def __init__(self, input_size=8, hidden_size=32, num_layers=1):
        super().__init__()
        self.lstm = nn.LSTM(input_size, hidden_size, num_layers, batch_first=True)

    def forward(self, x):
        # x shape: (batch, 63, 8)
        _, (h_n, _) = self.lstm(x)
        return h_n[-1]  # shape: (batch, hidden_size) — final hidden state
```

- Input: `(batch, 63, 8)` — 63-day window, 8 standardized indicators.
- Output: final hidden state, shape `(batch, hidden_size)`. Recommended `hidden_size=32` as a starting point — small enough to avoid overfitting on ~2500 samples per stock, large enough to capture indicator interactions. This is a tunable hyperparameter; do not over-invest in tuning per-stock (500 stocks × tuning = too expensive). Tune once on a representative sample of ~10-20 stocks and use the same architecture across all stocks.
- The LSTM here is being used as a **feature extractor**, not trained end-to-end to directly predict return. Its output (hidden state) becomes the input to the SVR. See Section 4.3 for how these two stages connect.

### 4.2 SVR stage

```python
from sklearn.svm import SVR

svr = SVR(kernel='rbf', C=5, epsilon=0.01)
```

- Input: the LSTM hidden state vector (32-dim, from 4.1).
- Output: scalar prediction `r̂ = target(t)`, the predicted 63-day forward return.
- **C=5, epsilon=0.01 are placeholder values from initial exploration — these must be tuned**, not used as final values. See Section 5 for the tuning procedure.

### 4.3 How LSTM and SVR connect (training procedure)

This is a two-stage pipeline, not a single end-to-end differentiable model. Implement as follows:

```
Step 1: Train the LSTM as an autoencoder-style or direct regressor on the
        training window to produce useful hidden states. Two options:

  Option A (simpler, recommended to start): Train the LSTM directly to
  predict the target return using a small linear head on top, e.g.:
      LSTM → hidden_state → Linear(hidden_size, 1) → predicted_return
  Train end-to-end with MSE loss. Once trained, DISCARD the linear head
  and keep only the LSTM. Use LSTM(x) on each window to produce a fixed
  hidden_state vector for every sample.

  Option B (more complex): Train LSTM as a sequence autoencoder
  (reconstruct the input window) so the hidden state captures general
  structure rather than being target-specific. Only pursue this if
  Option A's downstream SVR performance is unsatisfactory — it adds
  complexity without guaranteed benefit for this dataset size.

Step 2: Pass every sample's window through the trained LSTM (with the
        head removed) to get hidden_state vectors for ALL samples
        (train + validation).

Step 3: Train the SVR on (hidden_state, target_return) pairs from the
        TRAINING split only.

Step 4: Evaluate the SVR on the VALIDATION split's hidden states to get
        predictions, used to compute ωᵢ (Section 6).
```

Start with **Option A**. This is the standard, defensible approach and should be the default unless there's a clear empirical reason to switch.

---

## 5. Hyperparameter Tuning

Tune SVR's `C` and `epsilon` using grid search or random search, evaluated via the chronological validation split (Section 3). Suggested grid:

```python
param_grid = {
    'C': [0.1, 1, 5, 10, 50],
    'epsilon': [0.001, 0.01, 0.05, 0.1]
}
```

**Tuning granularity decision (must be made explicitly, do not assume):** tuning separately for all ~500 stocks is computationally expensive and may overfit small per-stock validation sets. Recommended default: tune once on a representative sample of liquid, large-cap stocks (e.g., 20-30 stocks spanning multiple sectors), pick a single (C, epsilon) pair, and apply it uniformly across all stocks. If results look poor for specific sectors, consider per-sector tuning as a middle ground. Document whichever choice is made — this is flagged as an open decision in `09_OPEN_DECISIONS.md`.

---

## 6. Computing ωᵢ (Per-Stock Residual Variance for Ω)

```python
predictions_val = svr.predict(hidden_states_val)
residuals = predictions_val - targets_val
omega_i = residuals.var()  # this is ωᵢ for this stock
```

**Critical constraint:** this MUST be computed on the validation set, never the training set. Training-set residuals will be artificially small (the model has already seen and fit that data), which would make Ω understate true uncertainty and cause Black-Litterman to over-trust the views. This was explicitly flagged as a risk during design — do not skip this check.

---

## 7. Walk-Forward Retraining Loop

This module's training procedure (Sections 4-6) must run **fresh at every rebalance date** during the backtest, using only the rolling 10-year window of data ending before that date.

```python
def train_and_predict_at_date(ticker: str, rebalance_date: date) -> dict:
    """
    1. Slice this ticker's feature data to [rebalance_date - 10 years, rebalance_date)
    2. Build 63-day windows + 63-day-forward targets within that slice
    3. Chronological train/val split within that slice (e.g., 80/20)
    4. Train LSTM (Section 4.1, Option A) on train split
    5. Extract hidden states for train + val
    6. Train SVR (Section 4.2) on train hidden states, with tuned hyperparams
    7. Predict on val → compute omega_i (Section 6)
    8. Predict r_hat for the MOST RECENT available 63-day window
       (i.e., the window ending at rebalance_date - 1, used to forecast
       the next 63 days forward from rebalance_date)
    Returns: {'ticker': ticker, 'r_hat': float, 'omega': float}
    """
```

This function is the core unit of work that the Backtest Engine (Module 7) will call once per stock at every rebalance date. With ~500 stocks and quarterly rebalancing over a multi-year backtest, this is the most computationally expensive part of the entire project — see Module 7 for caching and parallelization strategy.

---

## 8. Output Contract

At each rebalance date, this module produces, for every stock in the S&P 500 universe:

```python
{
    'ticker': str,
    'rebalance_date': date,
    'r_hat': float,      # predicted 63-day forward return
    'omega': float       # validation residual variance
}
```

Stored as `predictions/{rebalance_date}.parquet` with columns `[ticker, r_hat, omega]`, one row per stock. Module 4 (Stock Selection) consumes this file directly.
