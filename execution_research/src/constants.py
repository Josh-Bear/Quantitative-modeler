"""
constants.py — single source of truth for the execution-algorithm research.

Research question: for the SAME parent order, how much does each execution
algorithm (MARKET, TWAP, VWAP, POV) cost, and how does that depend on order
size, time of day and volatility?

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
# Bar label hours kept → 7 bars every trading day. 14:00 is dropped (missing on
# ~30 % of days, all of 2023, lunch-break volume); 00/01/09 are stray rows.
SESSION_HOURS = [10, 11, 12, 13, 15, 16, 17]
TRADING_DAYS_PER_YEAR = 252

# ─────────────────────────────────────────────────────────────────────────────
# Sample split
# ─────────────────────────────────────────────────────────────────────────────
IN_SAMPLE_END = "2024-12-31"     # ≤ this: calibrate the VWAP volume profile only
# > IN_SAMPLE_END: parent orders are drawn and executed (out-of-sample)

# ─────────────────────────────────────────────────────────────────────────────
# Universe — point-in-time Top-N by traded value
# ─────────────────────────────────────────────────────────────────────────────
TOP_N = 10                 # each day: the N names with the highest trailing ADV
ADV_DAYS = 20              # ADV = mean daily TRADING_VALUE over the previous 20 days (no look-ahead)

# ─────────────────────────────────────────────────────────────────────────────
# Parent orders (experiment design) — every algo executes the same set
# ─────────────────────────────────────────────────────────────────────────────
NAV_THB = 100_000_000.0
SIZE_BUCKETS_PCT_NAV = [0.01, 0.05, 0.10, 0.25]   # order notional = % of NAV → 1M / 5M / 10M / 25M THB
ORDERS_PER_BUCKET = 2_000
SEED = 20261124
LOT = 100
# Drop an order if any |hourly return| in its window exceeds this: prices are NOT
# corporate-action adjusted (BANPU +172 %, TRUE +63 %, ... in one hour).
JUMP_FILTER = 0.15

# ─────────────────────────────────────────────────────────────────────────────
# Algorithms — decision at Close_t, first child in bar t+1
# ─────────────────────────────────────────────────────────────────────────────
HORIZON_BARS = 7           # TWAP / VWAP / POV must finish within bars t+1 … t+7 (1 trading day)
POV_RATE = 0.10            # POV child = rate × that bar's actual traded value
SCHEDULE_CAP = 0.25        # TWAP / VWAP child ≤ this share of the bar's traded value (shortfall carries)
# MARKET has no cap: it takes the whole order in bar t+1 and pays the impact.
ALGOS = ["MARKET", "TWAP", "VWAP", "POV"]

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
    "POV_RATE": [0.05, 0.10, 0.20],
    "SCHEDULE_CAP": [0.10, 0.25],
}
