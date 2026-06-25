"""
constants.py — single source of truth for the bl_lstm_views pipeline.

Values here are the project's *design* values (from BL_LSTM_Project_Summary.md).
Where the original SET 2021-22 paper differs, the paper value is noted in a comment.

Tune the DEFAULT block for a fast, verifiable run; switch to the PAPER values to
reproduce the full study (much slower — see README).
"""
from __future__ import annotations

import os

# ─────────────────────────────────────────────────────────────────────────────
# Universe
# ─────────────────────────────────────────────────────────────────────────────
# Default: a small, sector-spread set so a full pipeline run finishes in minutes.
# Order matters only for reporting; market-cap weights come from live data.
DEFAULT_UNIVERSE = ["AAPL", "MSFT", "JNJ", "JPM", "XOM", "PG"]

# Smoke-test profile (`run.py --quick`): tiny universe + few epochs.
QUICK_UNIVERSE = ["AAPL", "MSFT"]

# The paper's full Dow Jones list (Table 5) — kept here so the study can be
# reproduced by pointing UNIVERSE at it (`run.py --full`).
FULL_UNIVERSE = [
    "AAPL", "MSFT",          # Technology
    "CAT", "MMM",            # Industrials
    "UNH", "JNJ",            # Healthcare
    "V", "GS",               # Financial Services
    "CVX", "XOM",            # Energy
    "WMT", "PG",             # Consumer Defensive
    "HD", "NKE",             # Consumer Cyclical
    "VZ", "DIS",             # Communication Services
    "DD",                    # Basic Materials
]

BENCHMARK = "SPY"  # backtest reference (paper used the market index per market)

# ─────────────────────────────────────────────────────────────────────────────
# Features — the 8 indicators (BL_LSTM_Project_Summary.md §3.2)
# ─────────────────────────────────────────────────────────────────────────────
FEATURES = [
    "macd",         # Trend     — EMA(12) - EMA(26)
    "rsi",          # Momentum  — 14-period RSI
    "squeeze_on",   # Volatility— BB inside KC (0/1)
    "bb_width",     # Volatility— Bollinger band width
    "kc_width",     # Volatility— Keltner channel width
    "sq_momentum",  # Momentum  — TTM squeeze momentum (linreg)
    "obv",          # Volume    — on-balance volume
    "hilbert",      # Cycle     — dominant cycle period (FFT approx of HT_DCPERIOD)
]

# ─────────────────────────────────────────────────────────────────────────────
# Sequence / forecast geometry
# ─────────────────────────────────────────────────────────────────────────────
TIME_WINDOW = 30   # look-back days fed to the LSTM (summary §4.1)
HORIZON = 5        # forecast 5 trading days ahead (~half a week; summary §4)

# ─────────────────────────────────────────────────────────────────────────────
# LSTM hyperparameters (summary §4.1, from grid search)
# ─────────────────────────────────────────────────────────────────────────────
LSTM_HIDDEN = 60
LSTM_LAYERS = 4
LSTM_DROPOUT = 0.30
LSTM_LR = 5e-3
LSTM_BATCH = 256
LSTM_EPOCHS = 20            # DEFAULT: fast. PAPER value:
PAPER_EPOCHS = 400          #   reproduce the study with this.
QUICK_EPOCHS = 3            # `--quick` smoke profile

# Architecture B (BL_LSTM_Implementation_Plan.md): ONE LSTM per stock that outputs
# all 8 indicators at once (Dense → 8), not 8 separate models. Training-loop extras
# mirror the plan's Keras callbacks:
LSTM_OUTPUTS = len(FEATURES)   # =8, multi-output head
EARLY_STOP_PATIENCE = 20       # stop if val loss hasn't improved in N epochs
LR_PLATEAU_PATIENCE = 10       # halve LR if val loss plateaus for N epochs
LR_PLATEAU_FACTOR = 0.5
LOG_EVERY = 100                # print train/val loss every N epochs

# ─────────────────────────────────────────────────────────────────────────────
# SVR hyperparameters (summary §4.2, from grid search)
# ─────────────────────────────────────────────────────────────────────────────
SVR_KERNEL = "rbf"
SVR_C = 5.0
SVR_EPSILON = 0.01

# The SVR predicts a STATIONARY price target — close relative to its own moving
# average, close(d)/SMA_REF(close)(d) - 1 — instead of the raw price level. An RBF
# SVR cannot extrapolate a trending level (2010-train prices vs 2025-test prices),
# so a level target collapses to garbage; the relative target stays ~0 and tracks.
REF_WINDOW = TIME_WINDOW

# Clamp the per-HORIZON view return to ±this before annualising, so one bad forecast
# can't blow μ_BL up (mirrors black_litterman_model's capQ / BugFix #3).
VIEW_Q_CAP = 0.25

# ─────────────────────────────────────────────────────────────────────────────
# Black-Litterman parameters (summary §6.2)
# ─────────────────────────────────────────────────────────────────────────────
BL_DELTA = 2.5             # risk-aversion δ (paper/zzz.py used 3.0)
BL_TAU = 0.05             # scaling τ
VIEW_CONFIDENCE = 0.5    # Idzorek view confidence (summary §4.1)
# Per-asset cap to limit drawdown (summary §4.1 = 10%). NOTE: a 10% cap is only
# feasible when n·cap ≥ 1, i.e. ≥10 names; for the small DEFAULT universe it would
# collapse to equal weight, so resolve_profile() raises it to an expressive value
# and reserves the paper's 0.10 for --full (the ~19-stock DJI universe).
MAX_WEIGHT = 0.10
MIN_WEIGHT = 0.0         # long-only floor (0 = no minimum)

# Ω (view uncertainty) is scaled from SVR MSE: low MSE → small Ω → trust the view
# more (summary §6.4). This multiplier maps a (normalised) MSE onto a variance.
OMEGA_SCALE = 1.0

# Trading-day annualisation factor for daily returns (BL covariance, Sharpe).
TRADING_DAYS = 252
RISK_FREE = 0.05         # annual risk-free rate for Sharpe (matches the JS app)

# ─────────────────────────────────────────────────────────────────────────────
# Date splits (summary §5.2). "today" in this repo is 2026; 2025 is complete.
# ─────────────────────────────────────────────────────────────────────────────
DATA_START = "2010-01-01"
TRAIN_START = "2010-01-01"
TRAIN_END = "2023-12-31"   # 14 years, many market regimes
VAL_START = "2024-01-01"
VAL_END = "2024-12-31"
TEST_START = "2025-01-01"
TEST_END = "2025-12-31"
DATA_END = "2026-01-01"     # download through end of test window

# ─────────────────────────────────────────────────────────────────────────────
# Data fetch
# ─────────────────────────────────────────────────────────────────────────────
RATE_LIMIT_SLEEP = 0.5     # seconds between yfinance calls (be polite)

# ─────────────────────────────────────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────────────────────────────────────
_SRC_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(_SRC_DIR)
OUTPUT_DIR = os.path.join(ROOT_DIR, "output")
CACHE_DIR = os.path.join(OUTPUT_DIR, "cache")
MODELS_DIR = os.path.join(OUTPUT_DIR, "models")
VIEWS_JSON = os.path.join(OUTPUT_DIR, "views.json")
REPORT_TXT = os.path.join(OUTPUT_DIR, "report.txt")


# ─────────────────────────────────────────────────────────────────────────────
# Run profiles — resolved by run.py from CLI flags
# ─────────────────────────────────────────────────────────────────────────────
def resolve_profile(profile: str = "default") -> dict:
    """Return the run config for a named profile: 'quick' | 'default' | 'full'.

    max_weight is scope-aware: small universes need a cap > 1/n to express views;
    --full uses the paper's 10% (feasible for the ~19-stock DJI list)."""
    if profile == "quick":
        return {"universe": list(QUICK_UNIVERSE), "epochs": QUICK_EPOCHS, "max_weight": 0.60}
    if profile == "full":
        return {"universe": list(FULL_UNIVERSE), "epochs": PAPER_EPOCHS, "max_weight": MAX_WEIGHT}
    return {"universe": list(DEFAULT_UNIVERSE), "epochs": LSTM_EPOCHS, "max_weight": 0.40}
