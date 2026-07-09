# Module 8: Evaluation Metrics & Reporting

**Depends on:** Module 7 (realized return time series)
**Produces output for:** Final report / presentation (this is the last module)

---

## 1. Goal

Compute standard performance and risk metrics on the backtest's realized returns, compare against the S&P 500 buy-and-hold benchmark, and produce diagnostic metrics on the ML model's quality. Compile all of this into a final report that explicitly discloses known limitations.

---

## 2. Return & Risk Metrics

All metrics computed on `realized_returns.parquet` from Module 7, **restricted to the performance period only** (per Module 7, Section 2 — dates `>= BACKTEST_START`).

```python
def annualized_return(period_returns: pd.Series, periods_per_year: int = 4) -> float:
    """periods_per_year = 4 since rebalancing is quarterly"""
    cumulative = (1 + period_returns).prod()
    n_years = len(period_returns) / periods_per_year
    return cumulative ** (1 / n_years) - 1

def annualized_volatility(period_returns: pd.Series, periods_per_year: int = 4) -> float:
    return period_returns.std() * np.sqrt(periods_per_year)

def sharpe_ratio(period_returns: pd.Series, risk_free_rate: float = 0.0, periods_per_year: int = 4) -> float:
    excess = period_returns - (risk_free_rate / periods_per_year)
    return (excess.mean() / excess.std()) * np.sqrt(periods_per_year)

def max_drawdown(portfolio_value: pd.Series) -> float:
    running_max = portfolio_value.cummax()
    drawdown = (portfolio_value - running_max) / running_max
    return drawdown.min()

def calmar_ratio(period_returns: pd.Series, portfolio_value: pd.Series, periods_per_year: int = 4) -> float:
    ann_return = annualized_return(period_returns, periods_per_year)
    mdd = abs(max_drawdown(portfolio_value))
    return ann_return / mdd if mdd > 0 else np.nan

def value_at_risk(period_returns: pd.Series, confidence: float = 0.95) -> float:
    return period_returns.quantile(1 - confidence)

def conditional_var(period_returns: pd.Series, confidence: float = 0.95) -> float:
    var = value_at_risk(period_returns, confidence)
    return period_returns[period_returns <= var].mean()
```

Note on `periods_per_year=4`: this backtest has quarterly (3-month) holding periods, so there are 4 realized-return observations per year, not 252 (daily) or 12 (monthly). Using the wrong annualization factor here is a common error — double check this matches the actual rebalance frequency.

---

## 3. Benchmark Comparison

Compute the same metrics (Section 2) for the **S&P 500 index, buy-and-hold**, over the identical performance period, using the same quarterly snapshot dates for an apples-to-apples comparison.

```python
def benchmark_returns(sp500_prices: pd.Series, rebalance_dates: List[date]) -> pd.Series:
    """
    Computes the SP500's own period return between consecutive rebalance
    dates, matching the strategy's holding periods exactly (same start/end
    dates) so the Sharpe/MDD/etc. comparison is fair.
    """
    returns = []
    for start, end in zip(rebalance_dates[:-1], rebalance_dates[1:]):
        p_start = sp500_prices.loc[start]
        p_end = sp500_prices.loc[end]
        returns.append((end, (p_end / p_start) - 1))
    return pd.Series(dict(returns))
```

Present strategy vs. benchmark side by side:

| Metric | Strategy | S&P 500 (B&H) |
|---|---|---|
| Annualized Return | ... | ... |
| Annualized Volatility | ... | ... |
| Sharpe Ratio | ... | ... |
| Max Drawdown | ... | ... |
| Calmar Ratio | ... | ... |
| VaR (95%) | ... | ... |
| CVaR (95%) | ... | ... |

---

## 4. ML Model Quality Diagnostics

These are separate from portfolio performance — they evaluate whether the LSTM+SVR predictions were actually useful, independent of how the BL/optimization layers used them. Important for understanding *why* the strategy did or didn't outperform.

### 4.1 Information Coefficient (IC)

Measures the rank correlation between predicted and actual returns, computed per rebalance date across all S&P 500 stocks (not just the 22 selected ones — this tells you about the predictive power of the full model, before selection bias kicks in).

```python
from scipy.stats import spearmanr

def information_coefficient(predictions: pd.DataFrame, actuals: pd.DataFrame) -> float:
    """
    predictions: [ticker, r_hat] for one rebalance date
    actuals: [ticker, actual_63day_return] — the REALIZED 63-day return
             that followed that rebalance date (only available in
             hindsight, computed after the fact for diagnostic purposes)
    """
    merged = predictions.merge(actuals, on='ticker')
    ic, _ = spearmanr(merged['r_hat'], merged['actual_63day_return'])
    return ic
```

Report the **mean IC across all rebalance dates**, and the **IC per sector** (does the model predict some sectors better than others?). As a rule of thumb in quantitative finance, IC > 0.05 is considered weakly predictive, IC > 0.1 is considered good for cross-sectional equity prediction — but report the actual number without over-interpreting it as "good" or "bad" without this context.

### 4.2 Directional Accuracy

```python
def directional_accuracy(predictions: pd.DataFrame, actuals: pd.DataFrame) -> float:
    merged = predictions.merge(actuals, on='ticker')
    correct_direction = (np.sign(merged['r_hat']) == np.sign(merged['actual_63day_return']))
    return correct_direction.mean()
```

Report overall and per-sector. 50% is the random-guessing baseline for a binary up/down call.

### 4.3 RMSE per Sector

```python
def rmse_per_sector(predictions: pd.DataFrame, actuals: pd.DataFrame, sector_map: dict) -> pd.DataFrame:
    merged = predictions.merge(actuals, on='ticker')
    merged['sector'] = merged['ticker'].map(sector_map)
    merged['sq_error'] = (merged['r_hat'] - merged['actual_63day_return']) ** 2
    return merged.groupby('sector')['sq_error'].apply(lambda x: np.sqrt(x.mean()))
```

---

## 5. Turnover Reporting

From Module 7's `turnover_log.csv`:

- Average % of the 22-stock universe that changes per rebalance.
- Total transaction costs paid over the full backtest (cumulative drag on returns).
- A simple bar chart or table: turnover % per rebalance date over time.

---

## 6. Rolling-Window Crisis Coverage (Required Limitation Disclosure)

Per the design discussion, the rolling 10-year training window will "forget" major crisis periods (e.g., 2008 GFC, 2020 COVID crash) once they fall outside the window. Compute and report, for each rebalance date, whether known crisis periods fall within that date's training window:

```python
KNOWN_CRISES = [
    ('2008-09-01', '2009-03-01'),  # Global Financial Crisis
    ('2020-02-01', '2020-04-01'),  # COVID crash
    # add others as relevant to the actual backtest period
]

def crisis_coverage(rebalance_date: date, rolling_window_years: int = 10) -> List[str]:
    window_start = rebalance_date - pd.DateOffset(years=rolling_window_years)
    covered = [
        name for name, (start, end) in KNOWN_CRISES
        if pd.Timestamp(start) >= window_start
    ]
    return covered
```

Report this as a simple table: rebalance date → which crisis periods were "visible" to the model's training data at that point. This directly explains why Σ-implied risk estimates (and therefore portfolio construction) might look different in early vs. late parts of the backtest.

---

## 7. Final Report Structure

Compile all of the above into a single report (Jupyter notebook, markdown, or PDF — Claude Code's choice based on what's easiest to generate from the existing pipeline) with these sections:

1. **Executive summary**: 2-3 sentences, did the strategy outperform the benchmark, on what basis.
2. **Cumulative return chart**: strategy vs. S&P 500, full performance period.
3. **Efficient Frontier visualization**: at 2-3 representative rebalance dates (e.g., start, middle, end of backtest) — plot the frontier curve with the Max Sharpe point marked.
4. **Performance metrics table**: Section 3's comparison table.
5. **ML quality diagnostics**: Section 4's IC, directional accuracy, RMSE — presented per sector.
6. **Turnover & cost analysis**: Section 5.
7. **Limitations** (explicit, do not omit or soften):
   - Survivorship bias (current S&P 500 list applied retroactively — see `01_DATA_PIPELINE.md` Section 5)
   - Rolling-window crisis coverage gaps (Section 6 above)
   - Market cap reconstruction approximation, if the fallback in `01_DATA_PIPELINE.md` Section 3.3 (Option B) was used
   - SVR hyperparameter tuning granularity (tuned once on a sample vs. per-stock — see `03_ML_MODEL.md` Section 5)
   - Sector classification held fixed for the entire backtest period despite real-world reclassifications
   - Any other approximations flagged during implementation (cross-reference `09_OPEN_DECISIONS.md`)

---

## 8. Output Contract

```
report/
├── final_report.ipynb (or .md / .pdf)
├── figures/
│   ├── cumulative_return.png
│   ├── efficient_frontier_{date}.png   (one per representative date)
│   └── turnover_over_time.png
└── tables/
    ├── performance_comparison.csv
    ├── ic_by_sector.csv
    └── crisis_coverage.csv
```
