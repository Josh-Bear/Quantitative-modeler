# Module 1: Data Pipeline

**Depends on:** nothing (this is the foundation)
**Produces output for:** Module 2 (Feature Engineering), Module 3 (ML Model), Module 5 (BL Model — needs market cap & sector)

---

## 1. Goal

Acquire and store all raw data needed for the rest of the pipeline, for the full S&P 500 universe, from 2010-01-01 to present. **No data currently exists — this must be built from scratch.**

---

## 2. Required Data Types

| Data | Granularity | Source | Notes |
|---|---|---|---|
| OHLCV price data | Daily, per stock | yfinance | Adjusted close required (for splits/dividends) |
| Market capitalization | Daily, per stock | yfinance gives current only — see Section 4 for historical workaround | Needed for mcap-weighted aggregation in Module 5 |
| GICS sector classification | Per stock | yfinance `.info['sector']` gives current only | Needed to define the 11 sectors; see Section 4 for historical caveat |
| S&P 500 constituent list | Point-in-time ideally, current list acceptable as fallback | See Section 5 | Determines which ~500 tickers are in the training universe |

---

## 3. Step-by-Step Implementation

### 3.1 Get the ticker universe

```python
import pandas as pd

# Wikipedia maintains a reasonably current S&P 500 constituent table
sp500_table = pd.read_html('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies')[0]
tickers = sp500_table['Symbol'].tolist()
sector_map = dict(zip(sp500_table['Symbol'], sp500_table['GICS Sector']))
```

This gives the **current** constituent list and **current** sector mapping. Flag for Module 9: this does not capture historical changes to the index or to sector classifications.

### 3.2 Download OHLCV history

```python
import yfinance as yf

raw_data = yf.download(
    tickers,
    start='2010-01-01',
    end=None,  # today
    group_by='ticker',
    auto_adjust=True,  # adjusted close handles splits/dividends
    threads=True
)
```

Implementation notes:
- Batch this in chunks (e.g., 50 tickers at a time) — yfinance bulk downloads of 500 tickers can be unreliable or rate-limited.
- Some tickers will fail (delisted, renamed, ticker changes). Log failures to a file (`failed_tickers.log`) rather than crashing the whole pipeline.
- Store the result as one Parquet file per ticker (`data/raw/prices/{ticker}.parquet`) rather than one giant DataFrame — this makes per-stock processing in Module 3 much faster and avoids loading 500 stocks into memory at once.

### 3.3 Market capitalization (historical workaround)

yfinance does not provide historical market cap directly. Two options, in order of preference:

**Option A (preferred): Reconstruct historical mcap**
```python
# mcap(t) = shares_outstanding(t) × close_price(t)
# yfinance gives current shares_outstanding via ticker.info['sharesOutstanding']
# Approximation: assume shares_outstanding is roughly constant over the
# lookback window (reasonable for large caps over a few years, less so
# over a full decade due to buybacks/issuance — flag as a known approximation)
shares_outstanding = yf.Ticker(ticker).info.get('sharesOutstanding')
mcap_series = price_series * shares_outstanding
```

**Option B (fallback): Use current mcap as a static weight**
If reconstructing historical mcap proves too unreliable across many tickers, fall back to using each stock's **current** market cap for all historical mcap-weighting calculations, and explicitly log this as a simplification in the final report (see `09_OPEN_DECISIONS.md`).

Do not silently pick one option — implement Option A first, and if data quality issues arise (e.g., shares outstanding unavailable for many tickers), fall back to Option B and log which tickers used the fallback.

### 3.4 Sector mapping

Use the GICS sector from Section 3.1 as the **fixed sector assignment for the entire backtest period.** Document this as a simplification: real GICS sector reassignments do happen but are infrequent enough that this is an acceptable simplification for this project (flag in `09_OPEN_DECISIONS.md` regardless).

Expected 11 sectors (GICS Level 1):
```
Energy, Materials, Industrials, Consumer Discretionary, Consumer Staples,
Health Care, Financials, Information Technology, Communication Services,
Utilities, Real Estate
```

---

## 4. Data Quality Checks (must implement before moving to Module 2)

Write a validation script that checks, per ticker:

1. **Date coverage**: does the series start near 2010-01-01 or later (newer listings)? Log the actual start date per ticker.
2. **Missing values**: gaps in the daily series (excluding weekends/holidays). Flag any ticker with >5% missing trading days.
3. **Stale prices**: runs of identical adjusted close for >10 consecutive days (often indicates a data error or trading halt).
4. **Outlier returns**: single-day returns >50% or <-50% not explained by a known split/merger — flag for manual review, do not auto-delete.

Output a `data_quality_report.csv` with one row per ticker summarizing these checks.

---

## 5. S&P 500 Survivorship Bias — Explicit Note

Using today's constituent list and applying it retroactively to 2010 means the backtest **excludes companies that were in the S&P 500 in the past but have since been removed** (bankruptcies, acquisitions, delistings), and **includes companies that weren't in the index for the full period** (recent additions).

This is a known limitation, not a bug. Do not attempt to source point-in-time historical constituents unless explicitly requested — that requires a paid data source (e.g., Bloomberg, CRSP, Compustat) that this project does not currently have access to. Document this limitation clearly in the final report (`08_EVALUATION_METRICS.md` → Limitations section).

---

## 6. Output Contract

After this module runs, the following must exist on disk for downstream modules:

```
data/
├── raw/
│   └── prices/
│       └── {ticker}.parquet         # columns: date, open, high, low, close, volume
├── reference/
│   ├── sector_map.csv               # columns: ticker, gics_sector
│   ├── mcap_history.parquet         # columns: date, ticker, market_cap (or static mcap if fallback used)
│   └── ticker_universe.csv          # final list of tickers successfully downloaded
├── failed_tickers.log
└── data_quality_report.csv
```

Module 2 (Feature Engineering) will read from `data/raw/prices/` and `data/reference/` directly.
