"""
constants.py — single source of truth for the execution-algorithm research.

Research question: for the SAME parent order, how much does each execution
algorithm (MARKET, TWAP, VWAP, POV10, POV5, POV5/10) cost, and how does that
depend on order size, time of day, volatility and year?

Values marked ASSUMPTION are not observable in the data (hourly OHLC + traded
value/volume, no bid/ask, no order book) and are varied in the sensitivity runs.
"""
from __future__ import annotations

from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# Paths — the hourly SET50 files live (gitignored) in ../order_execution/
# ─────────────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT.parent / "order_execution"
DATA_GLOB = "SET50_*.csv"
OUTPUT_DIR = ROOT / "output"

# ─────────────────────────────────────────────────────────────────────────────
# Bars
# ─────────────────────────────────────────────────────────────────────────────
# Bar label hours kept → 8 bars every trading day; 00/01/09 are stray rows and
# are dropped. The 14:00 bar (around the afternoon re-open) is missing on ~30 % of
# days (all of 2023): a missing bar is inserted with zero traded value (nothing can
# fill there, close carried forward) so every day has the same 8-bar grid.
SESSION_HOURS = [10, 11, 12, 13, 14, 15, 16, 17]
OPTIONAL_HOURS = [14]      # a day still counts as "full" for the VWAP profile without these
TRADING_DAYS_PER_YEAR = 252

# ─────────────────────────────────────────────────────────────────────────────
# Universe — 10 names locked for the whole backtest
# ─────────────────────────────────────────────────────────────────────────────
# Liquid SET50 names with full history from 2023-01 and no unadjusted
# corporate-action jumps (prices in the files are NOT adjusted: BANPU, TRUE,
# TIDLOR, DELTA ... show 15–170 % one-hour moves; GULF/THAI/MRDIYT start later).
TICKERS = ["KBANK", "CPALL", "ADVANC", "PTTEP", "AOT", "BBL", "SCB", "PTT", "KTB", "BDMS"]
ADV_DAYS = 20              # ADV = mean daily TRADING_VALUE over the previous 20 days (no look-ahead)
# VWAP volume profile: mean hourly share of daily value, pooled over TICKERS, over
# the previous PROFILE_DAYS trading days (rolling, no look-ahead). Orders start once
# ADV, profile and σ all exist → the backtest runs from ≈ Feb 2023.
PROFILE_DAYS = 21

# ─────────────────────────────────────────────────────────────────────────────
# Parent orders (experiment design) — every algo executes the same set
# ─────────────────────────────────────────────────────────────────────────────
NAV_THB = 100_000_000.0
SIZE_BUCKETS_PCT_NAV = [0.01, 0.05, 0.10, 0.25]   # order notional = % of NAV → 1M / 5M / 10M / 25M THB
ORDERS_PER_BUCKET = 2_000
SEED = 20261124
LOT = 100
# Safety net: redraw an order if any |hourly return| in its window exceeds this
# (prices are not corporate-action adjusted; none of TICKERS trips it).
JUMP_FILTER = 0.15

# ─────────────────────────────────────────────────────────────────────────────
# Algorithms — decision at Close_t, first child in bar t+1
# ─────────────────────────────────────────────────────────────────────────────
HORIZON_BARS = len(SESSION_HOURS)   # TWAP / VWAP / POV must finish within bars t+1 … t+8 (1 trading day)
SCHEDULE_CAP = 0.25        # TWAP / VWAP child ≤ this share of the bar's traded value (shortfall carries)
# MARKET has no cap: it takes the whole order in bar t+1 and pays the impact.

# POV child = rate(bar hour) × that bar's actual traded value. The SET lunch break
# (12:30–14:30) splits the day: morning = bars 10–13, afternoon = bars 14–17.
MORNING_HOURS = [10, 11, 12, 13]
AFTERNOON_HOURS = [14, 15, 16, 17]
POV_SCHEDULES = {
    "POV10": {h: 0.10 for h in SESSION_HOURS},
    "POV5": {h: 0.05 for h in SESSION_HOURS},
    "POV5/10": {**{h: 0.05 for h in MORNING_HOURS}, **{h: 0.10 for h in AFTERNOON_HOURS}},
}
ALGOS = ["MARKET", "TWAP", "VWAP", *POV_SCHEDULES]

# ─────────────────────────────────────────────────────────────────────────────
# Cost model — fill = bar VWAP ± (½ spread + impact)
# ─────────────────────────────────────────────────────────────────────────────
SPREAD_TICKS = 1.0         # ASSUMPTION — quoted spread in ticks (no bid/ask in data)
IMPACT_Y = 1.0             # ASSUMPTION — square-root law: Y × σ_hour × sqrt(child / bar value)
SIGMA_BARS = 100           # rolling window (bars) for ex-ante hourly σ (jumps excluded)
COMMISSION = 0.00157
VAT = 0.07
COMMISSION_ALL_IN = COMMISSION * (1.0 + VAT)

# SET tick-size table: (upper price bound, tick). Price < bound → tick.
SET_TICK_TABLE = [
    (2.0, 0.01), (5.0, 0.02), (10.0, 0.05), (25.0, 0.10),
    (100.0, 0.25), (200.0, 0.50), (400.0, 1.00), (float("inf"), 2.00),
]

# ─────────────────────────────────────────────────────────────────────────────
# Statistics / sensitivity
# ─────────────────────────────────────────────────────────────────────────────
BOOTSTRAP_N = 2_000
ALPHA = 0.05
SENSITIVITY = {                       # parameter → values (main value included)
    "SPREAD_TICKS": [1.0, 2.0],
    "IMPACT_Y": [0.5, 1.0, 2.0],
    "SCHEDULE_CAP": [0.10, 0.25],
}
