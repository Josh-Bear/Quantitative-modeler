# Module 4: Stock Selection (22-Stock Universe)

**Depends on:** Module 3 (predictions per stock at a given rebalance date)
**Produces output for:** Module 5 (BL Model — defines the 22-stock universe)

---

## 1. Goal

At each rebalance date, reduce the full S&P 500 universe down to **22 stocks**: the top 2 stocks (by predicted return) in each of the 11 GICS sectors. This selection is **dynamic** — it is re-computed at every rebalance date and the specific 22 tickers can change over time.

---

## 2. Selection Logic

```python
def select_universe(predictions: pd.DataFrame, sector_map: dict) -> pd.DataFrame:
    """
    Input:
        predictions: DataFrame with columns [ticker, r_hat, omega]
                      (output of Module 3 for one rebalance date)
        sector_map: dict mapping ticker -> GICS sector name

    Output:
        DataFrame with columns [ticker, sector, r_hat, omega, rank_in_sector]
        containing exactly 22 rows (assuming every sector has at least
        2 valid candidates — see Section 3 for edge cases).
    """
    df = predictions.copy()
    df['sector'] = df['ticker'].map(sector_map)
    df = df.dropna(subset=['sector'])  # drop tickers with no sector mapping

    df['rank_in_sector'] = df.groupby('sector')['r_hat'] \
                              .rank(ascending=False, method='first')

    selected = df[df['rank_in_sector'] <= 2].copy()
    selected = selected.sort_values(['sector', 'rank_in_sector'])

    return selected
```

This produces, per sector, a "top" stock (`rank_in_sector == 1`) and a "second" stock (`rank_in_sector == 2`). These labels (top/2nd) are used directly in Module 5 to construct the relative views.

---

## 3. Edge Cases to Handle

1. **Sector with fewer than 2 valid candidates.** This can happen if a sector has very few S&P 500 constituents, or if some stocks failed during data acquisition (Module 1) or model training (Module 3) and have no prediction for this rebalance date. Handle by:
   - Logging a warning with the rebalance date and affected sector.
   - If only 1 candidate exists, include it as the "top" stock for that sector, mark "2nd" as missing, and **skip the relative view for that sector only** in Module 5 (use only the absolute view). Do not crash the pipeline.
   - If 0 candidates exist, exclude that sector entirely for this rebalance date and reduce the universe size below 22 — log this clearly, do not pad with random stocks.

2. **Ties in r_hat.** Use `method='first'` in the rank (as shown above) to break ties deterministically by the original row order, rather than producing fractional ranks. Document that ties are broken arbitrarily by input order — this is a minor, acceptable simplification.

3. **NaN r_hat values.** Drop these before ranking (a stock with a failed prediction should not be eligible for selection). Log how many stocks were dropped at this step per rebalance date — if this number is consistently high, it indicates an upstream problem in Module 3 worth investigating.

---

## 4. Turnover Tracking (for later reporting)

Since the 22-stock universe changes at every rebalance, track how much it changes — this feeds into Module 8's reporting and Module 7's transaction cost calculation.

```python
def compute_universe_turnover(prev_universe: set, new_universe: set) -> dict:
    entered = new_universe - prev_universe
    exited = prev_universe - new_universe
    overlap_pct = len(prev_universe & new_universe) / len(prev_universe) if prev_universe else None
    return {
        'entered': entered,
        'exited': exited,
        'overlap_pct': overlap_pct
    }
```

Store this per rebalance date — Module 7 needs `entered`/`exited` to calculate transaction costs correctly (a stock that exits is fully sold, a stock that enters is bought from zero, not just a weight adjustment).

---

## 5. Output Contract

```python
# At each rebalance date, produces:
{
    'rebalance_date': date,
    'universe': pd.DataFrame[ticker, sector, r_hat, omega, rank_in_sector],  # 22 rows (or fewer, see edge cases)
    'turnover': dict  # from Section 4, None for the very first rebalance date
}
```

Stored as `universe/{rebalance_date}.parquet` (the DataFrame) plus `turnover_log.csv` (one row per rebalance date, appended over the backtest).

Module 5 reads `universe/{rebalance_date}.parquet` directly to know which 22 stocks to build BL views for, and uses the `rank_in_sector` column to identify which stock is "top" vs "2nd" within each sector for the relative view construction.
