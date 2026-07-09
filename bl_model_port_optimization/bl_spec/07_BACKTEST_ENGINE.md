# Module 7: Backtest Engine

**Depends on:** Modules 1-6 (calls them all, in sequence, at every rebalance date)
**Produces output for:** Module 8 (Evaluation Metrics — needs the realized return time series)

---

## 1. Goal

Run the full pipeline (Modules 3 through 6) repeatedly at each quarterly rebalance date across the backtest period, simulate holding the resulting portfolio for 3 months, account for transaction costs, and produce a realized return time series for evaluation.

---

## 2. Defining the Two Time Periods — Critical Distinction

This was an explicit point of confusion during design and must be implemented carefully:

```
2010 ─────────────────────── BACKTEST_START ─────────────────── present (2026)
│                                    │                                  │
│   Used only to:                    │     PERFORMANCE PERIOD:          │
│   - provide rolling 10yr training   │     - realized returns here      │
│     windows for the FIRST few       │       are what gets reported      │
│     rebalance dates                 │       as backtest performance     │
│   - estimate Σ, train models        │                                   │
│                                     │                                   │
│   NEVER counted as performance      │     Counted as performance       │
```

**`BACKTEST_START` must be set explicitly** (e.g., 2020-01-01 — chosen so there's at least 10 years of prior data for the rolling window, i.e., `BACKTEST_START >= 2010 + 10 years`). Returns realized before `BACKTEST_START` are never included in Sharpe/MDD/return calculations in Module 8, even though the data from before that date is actively used to train models and estimate Σ throughout the backtest (via the rolling window).

This is a configuration constant, not a hardcoded value — define it once at the top of the backtest config and reference it everywhere, so changing it doesn't require hunting through multiple files.

---

## 3. Rebalance Date Schedule

```python
def generate_rebalance_dates(backtest_start: date, backtest_end: date) -> List[date]:
    """
    Quarterly rebalancing — every 3 months from backtest_start to backtest_end.
    Should align to actual trading days (not calendar dates that might fall
    on a weekend/holiday) — snap to the nearest following trading day.
    """
    dates = pd.date_range(backtest_start, backtest_end, freq='3MS')  # quarter starts
    trading_calendar = ...  # use the actual trading days present in the price data from Module 1
    return [snap_to_next_trading_day(d, trading_calendar) for d in dates]
```

---

## 4. The Walk-Forward Loop

```python
def run_backtest(backtest_start: date, backtest_end: date, rolling_window_years: int = 10):
    rebalance_dates = generate_rebalance_dates(backtest_start, backtest_end)

    portfolio_value = 1.0  # normalized starting value
    current_holdings = {}  # ticker -> weight, empty initially
    realized_returns = []  # list of (date, return) for the PERFORMANCE PERIOD only

    for i, reb_date in enumerate(rebalance_dates):
        # ---- MODULE 3: train models, get predictions for ALL S&P 500 stocks ----
        # Each stock's training window is [reb_date - rolling_window_years, reb_date)
        predictions = {
            ticker: train_and_predict_at_date(ticker, reb_date)
            for ticker in sp500_universe
        }
        # See Section 5 for why this step needs caching/parallelization

        # ---- MODULE 4: select 22-stock universe ----
        universe = select_universe(predictions, sector_map)

        # ---- MODULE 5: construct BL inputs, get mu_BL ----
        bl_output = compute_bl_pipeline(universe, reb_date, rolling_window_years)

        # ---- MODULE 6: optimize, get w_star ----
        portfolio = max_sharpe_portfolio(bl_output['mu_BL'], bl_output['Sigma'])
        new_holdings = dict(zip(bl_output['stock_order'], portfolio['w_star']))

        # ---- Transaction costs from rebalancing ----
        cost = compute_transaction_cost(current_holdings, new_holdings, cost_rate=0.001)
        portfolio_value *= (1 - cost)

        # ---- Hold for 3 months, compute realized return ----
        next_reb_date = rebalance_dates[i+1] if i+1 < len(rebalance_dates) else backtest_end
        period_return = compute_realized_return(new_holdings, reb_date, next_reb_date)
        portfolio_value *= (1 + period_return)

        # Only record as "performance" if this period falls within the
        # designated performance window (Section 2)
        if reb_date >= backtest_start:
            realized_returns.append({
                'date': reb_date,
                'period_return': period_return,
                'transaction_cost': cost,
                'portfolio_value': portfolio_value
            })

        current_holdings = new_holdings

    return pd.DataFrame(realized_returns)
```

---

## 5. Computational Cost Warning — Must Address Before Implementing Naively

Training ~500 LSTM+SVR model pairs, at every one of (e.g.) 24 quarterly rebalance dates over a 6-year backtest, is **500 × 24 = 12,000 model training runs**. Even if each one is fast (a few seconds), this adds up to hours. Address this explicitly:

1. **Parallelize across stocks** within a single rebalance date — the 500 stocks' training are independent of each other. Use `multiprocessing` or `joblib.Parallel` to fan out across CPU cores.
2. **Cache intermediate results.** If the backtest is re-run multiple times during development (e.g., to test changes in Module 6 only), there's no need to retrain Module 3's models every time — cache `predictions/{rebalance_date}.parquet` (Module 3's output contract) to disk and skip retraining if the file already exists for a given (ticker, rebalance_date) pair.
3. **Start small for development.** When first getting the pipeline working end-to-end, run on a small subset (e.g., 2-3 rebalance dates, 30-50 stocks) before scaling to the full S&P 500 and full backtest period. This is a development/testing recommendation, not a change to the final scope.

---

## 6. Transaction Cost Calculation

```python
def compute_transaction_cost(old_holdings: dict, new_holdings: dict, cost_rate: float = 0.001) -> float:
    """
    cost_rate: 0.001 = 0.1% per trade, as decided during design.

    Cost is charged on the TURNOVER — the amount of portfolio value that
    needs to change hands, not on the full new portfolio value. This
    correctly handles:
      - Stocks held in both old and new portfolios: only the WEIGHT
        CHANGE incurs cost (or, simpler approximation: ignore minor
        weight rebalancing of held stocks and charge cost only on
        stocks that fully enter or exit the universe — flag as a
        simplification in 09_OPEN_DECISIONS.md if this approximation
        is used)
      - Stocks that exit (in old, not in new): fully sold, cost on
        their old weight
      - Stocks that enter (in new, not in old): fully bought, cost on
        their new weight
    """
    all_tickers = set(old_holdings.keys()) | set(new_holdings.keys())
    total_turnover = sum(
        abs(new_holdings.get(t, 0) - old_holdings.get(t, 0))
        for t in all_tickers
    )
    return total_turnover * cost_rate
```

Use the **full weight-change version** (not the simplified "only fully entering/exiting stocks" approximation) as the default — it's not meaningfully harder to implement and is more accurate. Only fall back to the simplification if performance profiling shows it's a bottleneck, which is unlikely.

---

## 7. Realized Return Calculation

```python
def compute_realized_return(holdings: dict, start_date: date, end_date: date) -> float:
    """
    Computes the portfolio's actual realized return over [start_date, end_date)
    by holding the given fixed weights (no further rebalancing within the period).
    """
    period_returns = {}
    for ticker, weight in holdings.items():
        prices = load_price_series(ticker, start_date, end_date)  # from Module 1's data
        stock_return = (prices.iloc[-1] / prices.iloc[0]) - 1
        period_returns[ticker] = stock_return

    portfolio_return = sum(weight * period_returns[ticker] for ticker, weight in holdings.items())
    return portfolio_return
```

**Note:** this computes a buy-and-hold return over the 3-month holding period (weights drift with price changes, no intra-period rebalancing), which is the standard and correct approach for this kind of backtest. Do not rebalance daily within the holding period unless explicitly requested — that would contradict the quarterly rebalance design decision.

---

## 8. Output Contract

```python
pd.DataFrame columns:
    date: date                  # rebalance date
    period_return: float        # realized return for that 3-month holding period
    transaction_cost: float     # cost charged at that rebalance
    portfolio_value: float      # cumulative normalized portfolio value
```

Saved as `backtest_results/realized_returns.parquet`. Also save, per rebalance date, the full intermediate state for debugging/reporting:

```
backtest_results/
├── realized_returns.parquet          # main output, feeds Module 8
├── universe_history.parquet           # which 22 stocks were held at each date (from Module 4)
├── weights_history.parquet            # w_star at each date (from Module 6)
└── turnover_log.csv                   # from Module 4, Section 4
```

Module 8 reads `realized_returns.parquet` as its primary input, and the other files for supplementary diagnostics (turnover stats, ML quality checks).
