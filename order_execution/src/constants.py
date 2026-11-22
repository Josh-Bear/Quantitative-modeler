"""
constants.py — single source of truth for the order_execution simulator.

Everything tunable lives here: data location, starting portfolio, signal
parameters, pre-trade rules, execution/cost model and SET market rules.

Values marked ASSUMPTION are not observable from the input (hourly OHLC +
traded value/volume, no bid/ask) and must be set by judgement.
"""
from __future__ import annotations

from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
DATA_GLOB = "SET50_*.csv"          # long-format hourly files in ROOT, one per year
OUTPUT_DIR = ROOT / "output"
EXCEL_PATH = OUTPUT_DIR / "order_execution.xlsx"
REPORT_PATH = OUTPUT_DIR / "report.txt"

# ─────────────────────────────────────────────────────────────────────────────
# Universe
# ─────────────────────────────────────────────────────────────────────────────
# The 10 most liquid SET50 names with full 2023→ history and no unadjusted
# corporate-action jumps (prices in the files are NOT adjusted: BANPU, TRUE,
# TIDLOR, DELTA show 30–170 % one-hour moves; GULF/THAI/MRDIYT start in 2025).
# None → the first N_STOCKS tickers in the data.
TICKERS: list[str] | None = ["KBANK", "CPALL", "ADVANC", "PTTEP", "AOT",
                             "BBL", "SCB", "PTT", "KTB", "BDMS"]
N_STOCKS = 10

# Hourly bars kept (bar label hour). 14:00 is dropped: it is missing on ~30 % of
# days (all of 2023) and sits in the lunch break; 00/01/09 are stray off-hours
# rows. What remains is 7 bars on every trading day.
SESSION_HOURS = [10, 11, 12, 13, 15, 16, 17]

# Used only by `run.py --synthetic` / test.py (GBM prices, no data file needed).
SYNTHETIC_TICKERS = {          # ticker: starting price (spans several tick bands)
    "PTT": 33.0, "AOT": 60.0, "CPALL": 55.0, "ADVANC": 230.0, "KBANK": 140.0,
    "SCB": 105.0, "BDMS": 27.0, "GULF": 45.0, "DELTA": 90.0, "TRUE": 8.5,
}
SYNTHETIC_DAYS = 250
SYNTHETIC_SIGMA_ANNUAL = 0.30
SYNTHETIC_SEED = 42
SYNTHETIC_HOURLY_VALUE_THB = 100_000_000.0   # mean traded value per bar (lognormal noise)

# ─────────────────────────────────────────────────────────────────────────────
# Starting portfolio
# ─────────────────────────────────────────────────────────────────────────────
INITIAL_NAV = 10_000_000.0        # THB
INITIAL_CASH_PCT = 0.0            # share of NAV held as cash at t0
# None → equal weight (1 - INITIAL_CASH_PCT) / n. Or {ticker: weight}.
INITIAL_WEIGHTS: dict[str, float] | None = None

# ─────────────────────────────────────────────────────────────────────────────
# Signal — SMA crossover + RSI filter (all events, never repeated states)
# ─────────────────────────────────────────────────────────────────────────────
SMA_FAST = 10
SMA_SLOW = 30
RSI_LEN = 14
RSI_BUY_MAX = 70.0        # BUY only while RSI < this
RSI_SELL = 80.0           # SELL when RSI crosses *up* through this
BUY_CONFIRM_BARS = 5      # a cross-up stays "armed" for this many bars (incl. the cross bar)
ATR_LEN = 14              # ATR proxy = mean |ΔClose| (no High/Low available)

# Order size: Δw = clip(K_DW × |Close − SMA_slow| / ATR, DW_MIN, DW_MAX)
K_DW = 0.01
DW_MIN = 0.01
DW_MAX = 0.05

# ─────────────────────────────────────────────────────────────────────────────
# Pre-trade rules
# ─────────────────────────────────────────────────────────────────────────────
W_MIN = 0.02
W_MAX = 0.25
# HOLD only rebalances once a drifted weight leaves [W_MIN − band, W_MAX + band];
# without a band a weight sitting on a bound re-triggers a tiny order every hour.
REBAL_BAND = 0.005
LOT = 100                  # SET board lot
MIN_ORDER_THB = 50_000.0   # drop orders smaller than this

# ─────────────────────────────────────────────────────────────────────────────
# Execution
# ─────────────────────────────────────────────────────────────────────────────
# Decision and arrival price are the close of bar t; the first slice fills at
# the close of bar t+1 (no same-bar fill).
STRATEGIES = {"MARKET": 1, "TWAP": 5}   # name: number of hourly slices
BENCH_BARS = 5                          # bars t+1 … t+BENCH_BARS for the TWAP / VWAP benchmarks
# Max share of the bar's actual TRADING_VALUE one child may take. The same
# per-bar traded value drives the square-root impact. (Uses the value of the bar
# being traded — known only once that bar ends; standard backtest convention.)
PARTICIPATION_CAP = 0.10

# ─────────────────────────────────────────────────────────────────────────────
# Cost model
# ─────────────────────────────────────────────────────────────────────────────
SPREAD_TICKS = 1.0         # ASSUMPTION — quoted spread in ticks (no bid/ask in data); each fill pays half
IMPACT_Y = 1.0             # square-root law coefficient
SIGMA_LEN = 100            # bars for the rolling hourly volatility
COMMISSION = 0.00157       # 0.157 % of traded value
VAT = 0.07                 # VAT on commission
COMMISSION_ALL_IN = COMMISSION * (1.0 + VAT)

# SET tick-size table: (upper price bound, tick). Price < bound → tick.
SET_TICK_TABLE = [
    (2.0, 0.01),
    (5.0, 0.02),
    (10.0, 0.05),
    (25.0, 0.10),
    (100.0, 0.25),
    (200.0, 0.50),
    (400.0, 1.00),
    (float("inf"), 2.00),
]

TRADING_DAYS_PER_YEAR = 252
