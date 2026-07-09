# Module 2: Feature Engineering (8 Technical Indicators)

**Depends on:** Module 1 (raw OHLCV data)
**Produces output for:** Module 3 (ML Model input features)

---

## 1. Goal

Compute 8 technical indicators per stock, per day, to be used as the LSTM's input features. The LSTM will consume a 63-day rolling window of these 8 indicators.

---

## 2. The 8 Indicators — Definitions & Formulas

Use the `ta` or `pandas-ta` Python library where possible rather than hand-rolling formulas, to reduce bugs. Hand-rolled formulas are given below as a fallback/reference.

### 2.1 RSI (Relative Strength Index)

Standard 14-period RSI:
```
RS = avg_gain(14) / avg_loss(14)
RSI = 100 - (100 / (1 + RS))
```
Library: `ta.momentum.RSIIndicator(close, window=14)`

### 2.2 ATR (Average True Range)

```
TR = max(high-low, |high-prev_close|, |low-prev_close|)
ATR = rolling_mean(TR, window=14)
```
Library: `ta.volatility.AverageTrueRange(high, low, close, window=14)`

### 2.3 MACD (Moving Average Convergence Divergence)

```
MACD_line = EMA(close, 12) - EMA(close, 26)
Signal_line = EMA(MACD_line, 9)
MACD_histogram = MACD_line - Signal_line
```
Use `MACD_histogram` as the feature (captures momentum shift, more stationary than the raw line).
Library: `ta.trend.MACD(close, window_slow=26, window_fast=12, window_sign=9)`

### 2.4 Keltner Channel

```
Middle = EMA(close, 20)
Upper = Middle + 2 × ATR(10)
Lower = Middle - 2 × ATR(10)
```
Feature to use: **position within channel** = `(close - Lower) / (Upper - Lower)`, bounded [0,1]-ish, more model-friendly than raw price levels.
Library: `ta.volatility.KeltnerChannel(high, low, close, window=20)`

### 2.5 Bollinger Bands (BB)

```
Middle = SMA(close, 20)
Upper = Middle + 2 × std(close, 20)
Lower = Middle - 2 × std(close, 20)
```
Feature to use: **%B** = `(close - Lower) / (Upper - Lower)` — standard normalized BB feature.
Library: `ta.volatility.BollingerBands(close, window=20, window_dev=2)`

### 2.6 Squeeze (TTM Squeeze On/Off)

Compares Bollinger Bands width to Keltner Channel width:
```
Squeeze_On = 1 if (BB_Upper < KC_Upper) and (BB_Lower > KC_Lower) else 0
```
This is binary (volatility compression indicator). Feed as 0/1 to the LSTM.
No standard library function — implement directly using BB and KC bounds from 2.4/2.5 above.

### 2.7 Momentum

Simple rate-of-change:
```
Momentum = close(t) - close(t - n),  n = 10 (standard)
```
Or normalized version (recommended, more comparable across stocks):
```
Momentum_pct = (close(t) / close(t-n)) - 1
```
Library: `ta.momentum.ROCIndicator(close, window=10)`

### 2.8 Hilbert Transform — Dominant Cycle Period

Uses the Hilbert Transform to estimate the dominant cycle period in the price series (from John Ehlers' work, popularized via TA-Lib).

```python
import talib
ht_dcperiod = talib.HT_DCPERIOD(close)
```

Note: this requires the **TA-Lib** C library (not `ta`/`pandas-ta`), which has a separate installation process (`pip install TA-Lib` requires the underlying C library to be installed first — on most systems via `conda install -c conda-forge ta-lib` is more reliable than pip). Flag this as an installation dependency Claude Code should resolve early, since it's the most likely indicator to cause environment setup issues.

---

## 3. Implementation Structure

```python
def compute_indicators(ohlcv_df: pd.DataFrame) -> pd.DataFrame:
    """
    Input: DataFrame with columns [date, open, high, low, close, volume]
           for a single ticker, sorted by date ascending.
    Output: DataFrame with columns [date, rsi, atr, macd_hist, keltner_pos,
             bb_pctb, squeeze_on, momentum_pct, ht_dcperiod]
    """
    ...
```

Run this once per ticker, reading from `data/raw/prices/{ticker}.parquet`, writing to `data/features/{ticker}.parquet`.

---

## 4. Critical Implementation Notes

1. **Warm-up period.** Every indicator above needs a lookback window to compute (longest is MACD's 26-period EMA + 9-period signal ≈ 35 days, or HT_DCPERIOD which needs ~50 bars to stabilize). The first ~50 rows of each ticker's indicator series will be NaN or unreliable. **Drop these rows** before they ever reach Module 3 — do not let the LSTM train on indicator values computed from insufficient warm-up data.

2. **Normalization.** RSI (0-100), %B (~0-1), Squeeze (0/1), and HT_DCPERIOD (raw period in days, can be 10-50) are on very different scales. Before feeding to the LSTM in Module 3, **standardize each indicator** (z-score, fit on training data only, applied to validation/test) — do not let one indicator dominate due to scale alone. This standardization must respect the walk-forward constraint: fit scalers only on the rolling training window available at each point in time, never on future data.

3. **No look-ahead in indicator computation itself.** All indicators above are computed using only past data (rolling windows looking backward), which is correct by construction. The risk is in the *standardization* step (item 2) — that's where look-ahead bias commonly creeps in if scalers are fit on the full dataset instead of per-window.

---

## 5. Output Contract

```
data/
└── features/
    └── {ticker}.parquet
        # columns: date, rsi, atr, macd_hist, keltner_pos, bb_pctb,
        #          squeeze_on, momentum_pct, ht_dcperiod
        # (NaN warm-up rows already dropped)
```

Module 3 will read this file per ticker, apply walk-forward standardization, and construct 63-day rolling windows as LSTM input sequences.
