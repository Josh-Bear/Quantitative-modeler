"""
constants.py — single source of truth for the ML-driven Black-Litterman
portfolio-optimization pipeline.

Every value flagged as a *locked design decision* in bl_spec/00_OVERVIEW.md
section 4 lives here verbatim, and every *documented default* from
bl_spec/09_OPEN_DECISIONS.md is resolved here with a `# 09 §N` reference.
Do not silently change a locked decision — flag it (see 00_OVERVIEW.md §4).
"""
from __future__ import annotations

import os
from datetime import date

# ─────────────────────────────────────────────────────────────────────────────
# Dates  (00 §4: "Data history 2010 to present"; 09 §8: BACKTEST_START)
# ─────────────────────────────────────────────────────────────────────────────
DATA_START = "2010-01-01"
DATA_END = date.today().strftime("%Y-%m-%d")          # "present"

# 09 §8 — the one item with no spec default; user-confirmed 2020-01-01.
# Must be >= DATA_START + ROLLING_WINDOW_YEARS so the first rebalance has a
# full 10-year training window. Returns before this date are NEVER counted as
# performance (07 §2) — they only feed the rolling window / Σ estimation.
BACKTEST_START = "2020-01-01"
BACKTEST_END = DATA_END

# ─────────────────────────────────────────────────────────────────────────────
# Walk-forward geometry  (00 §4)
# ─────────────────────────────────────────────────────────────────────────────
ROLLING_WINDOW_YEARS = 10        # fixed-size rolling training window
REBALANCE_FREQ = "3MS"           # quarterly (every 3 months, quarter starts)
INPUT_WINDOW = 63                # trading days fed to the LSTM — 1:1 with HORIZON
                                 #   (window = forecast horizon; see 03_ML_MODEL.md §2)
HORIZON = 63                     # 63-trading-day forward return (the target)
TRADING_DAYS = 252               # annualisation / unit conversions

# Σ is built from DAILY returns then scaled to the 63-day horizon so it is
# unit-consistent with Q and Π (05 §7). Variance scales linearly with time.
HORIZON_SCALE = HORIZON          # multiply daily Σ by this → 63-day Σ

# ─────────────────────────────────────────────────────────────────────────────
# Features — the 8 technical indicators  (00 §4, spec 02)
# ─────────────────────────────────────────────────────────────────────────────
FEATURES = [
    "rsi",           # 2.1 RSI(14)
    "atr",           # 2.2 ATR(14)
    "macd_hist",     # 2.3 MACD histogram (line - signal)
    "keltner_pos",   # 2.4 position within Keltner channel
    "bb_pctb",       # 2.5 Bollinger %B
    "squeeze_on",    # 2.6 TTM squeeze on/off (0/1)
    "momentum_pct",  # 2.7 10-day rate-of-change
    "ht_dcperiod",   # 2.8 Hilbert transform dominant cycle period (TA-Lib)
]
N_FEATURES = len(FEATURES)       # = 8 (LSTM input_size)

# Warm-up rows to drop before features reach the model (02 §4.1). The longest
# lookback is MACD(26)+signal(9) ≈ 35 and HT_DCPERIOD which needs ~50 bars.
WARMUP_DROP = 50

# ─────────────────────────────────────────────────────────────────────────────
# LSTM  (spec 03 §3.1) — feature extractor, Option A (09 §5)
# ─────────────────────────────────────────────────────────────────────────────
LSTM_HIDDEN = 64                 # hidden state size (= SVR input dim)
LSTM_LAYERS = 4
LSTM_DROPOUT = 0.4               # dropout between LSTM layers (ignored if LSTM_LAYERS=1)
LSTM_LR = 0.005
LSTM_BATCH = 32
LSTM_EPOCHS = 600                # default profile; overridden per run profile
LSTM_PATIENCE = 30               # early stopping: stop if val MSE doesn't improve for N epochs
VAL_FRACTION = 0.20              # chronological last-20% validation split (03 §2)

# ─────────────────────────────────────────────────────────────────────────────
# SVR  (spec 03 §3.2, §4) — predicts the 63-day return from the hidden state
# ─────────────────────────────────────────────────────────────────────────────
SVR_KERNEL = "rbf"
# Placeholder values from the spec; the real values are chosen by tuning once on
# a representative sample and applied uniformly (09 §4). See SVR_TUNE_GRID.
SVR_C = 5.0
SVR_EPSILON = 0.01
SVR_TUNE_GRID = {
    "C": [0.1, 1, 5, 10, 50],
    "epsilon": [0.001, 0.01, 0.05, 0.1],
}
# Number of liquid, sector-diverse stocks used to tune (C, ε) once (09 §4).
SVR_TUNE_SAMPLE = 20

# ─────────────────────────────────────────────────────────────────────────────
# Black-Litterman  (00 §4)
# ─────────────────────────────────────────────────────────────────────────────
BL_DELTA = 2.5                   # risk aversion δ (fixed)
BL_TAU = 0.05                    # scaling τ (fixed)
RIDGE_EPS = 1e-6                 # relative ridge added to Σ if ill-conditioned (05 §9)
COND_WARN = 1e10                 # condition-number warning threshold (05 §9)

# ─────────────────────────────────────────────────────────────────────────────
# Stock selection  (00 §4, spec 04)
# ─────────────────────────────────────────────────────────────────────────────
N_PER_SECTOR = 2                 # top-2 per sector
GICS_SECTORS = [                 # the 11 GICS Level-1 sectors (spec 01 §3.4)
    "Energy", "Materials", "Industrials", "Consumer Discretionary",
    "Consumer Staples", "Health Care", "Financials",
    "Information Technology", "Communication Services",
    "Utilities", "Real Estate",
]
N_SECTORS = len(GICS_SECTORS)    # = 11  → 22-stock target universe

# ─────────────────────────────────────────────────────────────────────────────
# Optimization  (00 §4, spec 06)
# ─────────────────────────────────────────────────────────────────────────────
ALLOW_SHORT = False              # long-only default (09 §6)
FRONTIER_POINTS = 50

# ─────────────────────────────────────────────────────────────────────────────
# Backtest  (00 §4)
# ─────────────────────────────────────────────────────────────────────────────
TRANSACTION_COST = 0.001         # 0.1% per trade, charged on full turnover (09 §7)
PERIODS_PER_YEAR = 4             # quarterly rebalancing → 4 obs/year (08 §2)

# 09 §10 — risk-free rate: pull 3-month T-bill (FRED DTB3) if reachable, else 0.0.
RISK_FREE_FRED_SERIES = "DTB3"
RISK_FREE_FALLBACK = 0.0         # annualised; converted to 63-day units where needed

# Known crisis windows for the rolling-window coverage disclosure (08 §6).
KNOWN_CRISES = [
    ("Global Financial Crisis", "2008-09-01", "2009-03-01"),
    ("COVID crash", "2020-02-01", "2020-04-01"),
]

# ─────────────────────────────────────────────────────────────────────────────
# Data fetch
# ─────────────────────────────────────────────────────────────────────────────
BENCHMARK = "^GSPC"              # S&P 500 index for the buy-&-hold benchmark (08 §3)
DOWNLOAD_CHUNK = 50              # tickers per yfinance bulk call (01 §3.2)
RATE_LIMIT_SLEEP = 0.5           # seconds between yfinance .info calls (be polite)
WIKI_SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"

# DEVIATION from 00 §4 ("Universe (ML training): S&P 500, ~500 stocks"), approved
# by Josh 2026-07-02 after reviewing an actual --full run: 500 stocks × 26
# quarterly rebalances took 15-20+ hours (nohup.out shows a manual Ctrl-C at
# rebalance 15/26) and the live universe used by `--full` was replaced with the
# S&P 100 wholesale rather than left as S&P 500 — not a silent change, see
# CLAUDE.md "Key design decisions" and bl_spec/09_OPEN_DECISIONS.md §11.
WIKI_SP100_URL = "https://en.wikipedia.org/wiki/S%26P_100"

# ─────────────────────────────────────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────────────────────────────────────
_SRC_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(_SRC_DIR)
DATA_DIR = os.path.join(ROOT_DIR, "data")
RAW_PRICES_DIR = os.path.join(DATA_DIR, "raw", "prices")
FEATURES_DIR = os.path.join(DATA_DIR, "features")
REFERENCE_DIR = os.path.join(DATA_DIR, "reference")
OUTPUT_DIR = os.path.join(ROOT_DIR, "output")
PREDICTIONS_DIR = os.path.join(OUTPUT_DIR, "predictions")
UNIVERSE_DIR = os.path.join(OUTPUT_DIR, "universe")
BL_DIR = os.path.join(OUTPUT_DIR, "bl_outputs")
PORTFOLIO_DIR = os.path.join(OUTPUT_DIR, "portfolios")
BACKTEST_DIR = os.path.join(OUTPUT_DIR, "backtest_results")
REPORT_DIR = os.path.join(OUTPUT_DIR, "report")


def ensure_dirs() -> None:
    """Create every output/data directory the pipeline writes to."""
    for d in (RAW_PRICES_DIR, FEATURES_DIR, REFERENCE_DIR, PREDICTIONS_DIR,
              UNIVERSE_DIR, BL_DIR, PORTFOLIO_DIR, BACKTEST_DIR,
              os.path.join(REPORT_DIR, "figures"),
              os.path.join(REPORT_DIR, "tables")):
        os.makedirs(d, exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# Run profiles
# ─────────────────────────────────────────────────────────────────────────────
# The full spec scope is ~500 stocks × ~26 quarterly rebalances × per-stock LSTM
# training = thousands of model fits = hours (07 §5). The profiles below let the
# pipeline run end-to-end on a small slice for development, then scale to the
# paper scope. This is a dev convenience (07 §5), NOT a change to the locked
# design — 'full' runs the spec as written.
#
# QUICK_UNIVERSE: exactly 2 liquid names per GICS sector (22 tickers) so the
# whole pipeline — including top-2/sector selection and the 11+11 views — is
# exercised even on the smoke profile. Sectors here match FALLBACK_SECTOR_MAP.
QUICK_UNIVERSE = [
    "XOM", "CVX",        # Energy
    "LIN", "SHW",        # Materials
    "CAT", "HON",        # Industrials
    "AMZN", "HD",        # Consumer Discretionary
    "PG", "KO",          # Consumer Staples
    "JNJ", "UNH",        # Health Care
    "JPM", "BAC",        # Financials
    "AAPL", "MSFT",      # Information Technology
    "GOOGL", "META",     # Communication Services
    "NEE", "DUK",        # Utilities
    "PLD", "AMT",        # Real Estate
]

# A current-sector map for the quick universe so the universe step works offline
# (the full universe still uses the live Wikipedia table in M1).
FALLBACK_SECTOR_MAP = {
    "XOM": "Energy", "CVX": "Energy",
    "LIN": "Materials", "SHW": "Materials",
    "CAT": "Industrials", "HON": "Industrials",
    "AMZN": "Consumer Discretionary", "HD": "Consumer Discretionary",
    "PG": "Consumer Staples", "KO": "Consumer Staples",
    "JNJ": "Health Care", "UNH": "Health Care",
    "JPM": "Financials", "BAC": "Financials",
    "AAPL": "Information Technology", "MSFT": "Information Technology",
    "GOOGL": "Communication Services", "META": "Communication Services",
    "NEE": "Utilities", "DUK": "Utilities",
    "PLD": "Real Estate", "AMT": "Real Estate",
}

# DEFAULT_UNIVERSE: ~4 names per sector (44 tickers) — a richer slice that lets
# top-2 selection actually choose between candidates, still finishes in a
# reasonable time. Extends the quick set; sectors resolved live in M1.
DEFAULT_UNIVERSE = QUICK_UNIVERSE + [
    "COP", "SLB",        # Energy
    "FCX", "NEM",        # Materials
    "GE", "UPS",         # Industrials
    "TSLA", "MCD",       # Consumer Discretionary
    "WMT", "COST",       # Consumer Staples
    "LLY", "ABBV",       # Health Care
    "BRK-B", "V",        # Financials
    "NVDA", "AVGO",      # Information Technology
    "GOOG", "NFLX",      # Communication Services
    "SO", "D",           # Utilities
    "EQIX", "SPG",       # Real Estate
]


def resolve_profile(profile: str = "default") -> dict:
    """Map a CLI profile name to a concrete run config.

    'full' = live S&P 100 universe (narrowed from the spec's S&P 500 — see
    get_universe()'s docstring and 09_OPEN_DECISIONS.md §11), full quarterly
    schedule, full epochs. 'quick'/'default' shrink universe, rebalance count
    and epochs for development (07 §5).
    """
    if profile == "quick":
        return {
            "universe": list(QUICK_UNIVERSE),
            "epochs": 5,
            "max_rebalances": 2,        # only run the first N rebalance dates
            "tune_svr": False,          # use placeholder (C, ε) to stay fast
        }
    if profile == "full":
        return {
            "universe": None,           # None → live S&P 100 list from Wikipedia
            "epochs": 100,
            "max_rebalances": None,     # full quarterly schedule
            "tune_svr": True,
        }
    # default
    return {
        "universe": list(DEFAULT_UNIVERSE),
        "epochs": 30,
        "max_rebalances": 4,
        "tune_svr": True,
    }
