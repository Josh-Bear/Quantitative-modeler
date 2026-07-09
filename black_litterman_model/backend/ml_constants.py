"""
ml_constants.py — hyperparameters for the web-app LSTM+SVR view generator
(backend/ml_views.py)

Separate from bl_model_port_optimization/src/constants.py which drives the
full backtest pipeline. The web app trades some accuracy for speed:
  - shorter input window (30 vs 63)
  - larger batch for faster epochs (LSTM_BATCH=64 vs the pipeline's 32)
  - shorter early-stopping patience (LSTM_PATIENCE=25 vs the pipeline's 30)
  - lower LR (0.001 vs 0.005)
"""

# ── Data / window geometry ────────────────────────────────────────────
WINDOW       = 30      # LSTM input window (trading days)
HORIZON      = 63      # forward-return target horizon (trading days)
FETCH_PERIOD = "2y"    # yfinance history period
WARMUP_DROP  = 50      # leading rows dropped after indicator computation
MIN_ROWS     = 200     # minimum usable rows per ticker after warm-up

# ── Train / validation split ──────────────────────────────────────────
VAL_FRACTION = 0.20    # chronological last-20% for validation (never shuffled)
MIN_TRAIN    = 20      # minimum training samples before we give up on a ticker
MIN_VAL      = 5       # minimum validation samples

# ── LSTM ─────────────────────────────────────────────────────────────
LSTM_HIDDEN   = 64     # hidden state size (= SVR input dimension)
LSTM_LAYERS   = 4      # stacked LSTM layers
LSTM_DROPOUT  = 0.4    # dropout between layers (ignored when LSTM_LAYERS=1)
LSTM_LR       = 0.001  # Adam learning rate
LSTM_BATCH    = 64    # mini-batch size (larger than pipeline for speed)
LSTM_EPOCHS   = 250     # default request value for /api/ml-views (callers may override;
                        # the legacy vanilla-JS UI always overrides down to 30 for speed)
LSTM_PATIENCE = 25     # early-stopping patience (epochs with no val improvement)

# ── SVR ──────────────────────────────────────────────────────────────
SVR_KERNEL  = "rbf"
SVR_C       = 5.0
SVR_EPSILON = 0.01

# ── Black-Litterman ───────────────────────────────────────────────────
BL_TAU   = 0.05   # default τ (overridden by request)
BL_DELTA = 2.5    # default δ (overridden by request)

# Annualisation: SVR returns 63-day returns; the JS engine uses annualised Σ.
# Q must be in the same unit → multiply by ANNUALISE.
# omega (variance of residuals) scales as ANNUALISE².
ANNUALISE = 252.0 / HORIZON   # ≈ 4.0

# ── Numerical guards ─────────────────────────────────────────────────
OMEGA_FLOOR = 1e-6   # Ω diagonal floor — prevents singular matrix in JS engine
