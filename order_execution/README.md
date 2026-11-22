# order_execution — SET50 hourly order-execution simulator

Simulates the full path from market data to filled orders for a 10-stock SET50
portfolio on **hourly bars**, and compares two ways of sending the same orders
to the market:

```
hourly bars → signal (BUY/HOLD/SELL) → pre-trade checks → execution (MARKET vs TWAP) → metrics
```

## Run

```bash
pip install -r requirements.txt
python run.py                       # every SET50_*.csv in this folder
python run.py --csv a.csv b.csv     # explicit file(s)
python run.py --synthetic           # GBM prices + volume, no data needed
python test.py                      # 38 sanity checks, no network
```

Outputs: `output/order_execution.xlsx` (7 sheets) and `output/report.txt`.
`Order_Execution.ipynb` walks the same pipeline step by step with charts.

## Data

Long format, one or more CSVs (one per year — `SET50_2023.csv` … `SET50_2026.csv`,
gitignored). Required columns, matched case-insensitively:
`TICKER, DATE, CLOSE_PRC, TRADING_VALUE, TRADING_VOLUME` (other columns are ignored).

Cleaning (`src/data_loader.py`):

* Only bars labelled **10, 11, 12, 13, 15, 16, 17** are kept (`SESSION_HOURS`) → 7 bars
  every trading day. The 14:00 bar is dropped (missing on ~30 % of days, all of 2023,
  lunch-break volume); stray 00:00 / 01:00 / 09:00 rows are dropped.
* A ticker with no row in a bar: close is forward-filled, traded value = 0 → nothing can
  fill in that bar.
* **Prices are not adjusted for corporate actions** (BANPU +172 %, TRUE +63 %, TIDLOR +32 %
  in one hour; GULF / THAI / MRDIYT only start in 2025). `TICKERS` is therefore fixed to the
  10 most liquid names with full history and no such jumps:
  KBANK, CPALL, ADVANC, PTTEP, AOT, BBL, SCB, PTT, KTB, BDMS.

## Pipeline

| Stage | Module | What it does |
|---|---|---|
| Signal | `signals.py` | SMA(10/30) crossover + RSI(14) filter on closes, all **events** (fire once). BUY = cross-up within the last 5 bars, still above, RSI < 70, once per cross. SELL = cross-down, or RSI crosses up through 80. Size Δw = clip(1% × \|Close − SMA30\| / ATR, 1%, 5%), ATR = mean \|ΔClose\| |
| Pre-trade | `pretrade.py` | weight bounds [2%, 25%] → board lot 100 → no short → min order 50k THB → cash (sells first, buys scaled to fit) → one open order per ticker → post-trade weight check. Every reject/adjust is logged |
| Execution | `execution.py`, `cost_model.py` | Decision and **arrival price at Close_t; first fill at Close_{t+1}**. MARKET = 1 slice (bar t+1), TWAP = 5 slices (bars t+1 … t+5). Fill = Close ± (½ tick + square-root impact on the bar's traded value). Each child ≤ 10 % of that bar's actual `TRADING_VALUE`; what a slice cannot fill carries to the next; unfilled after the last slice is cancelled |
| Simulation | `simulator.py` | one portfolio per strategy, same prices and signals |
| Metrics | `metrics.py` | avg fill price, fill rate, Implementation Shortfall vs arrival split into timing / spread / impact / commission / opportunity, avg fill vs TWAP and vs **market VWAP** (Σvalue / Σvolume over bars t+1 … t+5), NAV / return / Sharpe / drawdown / turnover |

## Assumptions to keep in mind

* **No bid/ask in the data.** Close is treated as mid and the spread is 1 tick
  (`SPREAD_TICKS`). Half-spread + commission are most of the cost at a 10 M THB portfolio,
  so this assumption drives the IS level.
* The participation cap and impact use the traded value **of the bar being traded**, which
  is only known once that bar ends — the usual backtest convention, a mild look-ahead.
* A MARKET order whose next bar has no trading is cancelled (opportunity cost), not held.
* TWAP skips new signals for a ticker while its order is still working (`ACTIVE_ORDER`
  rejects), so MARKET and TWAP do not trade an identical set of orders.
* The cost-inclusive fill price is **not** snapped to the tick grid (it is an average
  sweep price; snapping mid + ½ tick up would charge a full tick).
* σ for impact is the rolling std of hourly close returns, overnight bars included.
* Settlement is immediate (no T+2): sale proceeds fund buys in the same bar.
* HOLD rebalances a drifted weight only once it leaves the bounds by more than
  `REBAL_BAND` (0.5%), otherwise a weight sitting on a bound would re-trigger every hour.
* Limit orders and a VWAP *strategy* are out of scope (VWAP is used as a benchmark only).

All parameters live in `src/constants.py`.
