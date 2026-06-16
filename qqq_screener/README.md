# QQQ High Growth Screener

Screens NASDAQ-100 constituents (by default, those ranked 26–100 by market cap)
against a 5-point high-growth checklist using live data from yfinance. Outputs a
scored console table and a 3-sheet Excel workbook.

## Run

```bash
cd qqq_screener
pip install yfinance pandas numpy openpyxl requests lxml
python run.py
# output → qqq_screener/output/qqq_screener_output.xlsx
```

A full run makes ~175 yfinance calls (ranking + screening) with a 0.5s delay
between each, so expect a few minutes.

## Config

All user-tunable settings live at the top of `src/constants.py`:

| Setting | Default | Meaning |
|---------|---------|---------|
| `RANK_MIN` / `RANK_MAX` | 26 / 100 | Market-cap rank window to screen |
| `REV_GROWTH_THRESHOLD` | 0.15 | Check 1 pass line |
| `GROSS_MARGIN_THRESHOLD` | 0.50 | Check 3 pass line |
| `RULE_OF_40_THRESHOLD` | 40.0 | Check 4 pass line |
| `BUY_SCORE` / `WATCH_SCORE` | 5 / 4 | Signal cutoffs |
| `RATE_LIMIT_SLEEP` | 0.5 | Seconds between yfinance calls |

## The Checklist

Each ticker scores 0–5. A check is **pass** / **fail** / **N/A** (N/A = data
missing; not counted toward the score).

| # | Check | Passes when | Source |
|---|-------|-------------|--------|
| 1 | Revenue growth | `revenueGrowth` > 15% | yfinance `.info` |
| 2 | Revenue accelerating | latest-quarter YoY growth > most-recent full-year YoY growth | quarterly + annual income stmt |
| 3 | Gross margin high & expanding | `grossMargins` > 50% **and** latest FY gross margin > prior FY | `.info` + annual income stmt |
| 4 | Rule of 40 | revenue growth % + FCF margin % > 40 | FCF = operating CF + capex |
| 5 | Analyst revising up | `forwardEps` > `trailingEps` | `.info` |

**Signal:** 5/5 → 🟢 BUY · 4/5 → 🟡 WATCH · ≤3/5 → 🔴 SKIP

### Interpretation notes
- **Check 2** uses date-aware matching for the year-ago quarter (yfinance
  quarterly columns are irregularly spaced), comparing the latest quarter's YoY
  growth to the trailing full-year pace.
- **Check 3** requires *both* a high level and YoY expansion. A very high but
  slightly contracting margin (common for mature software names) fails this check
  by design.
- Negative FCF still computes a Rule of 40 score but is flagged in the Data
  Quality notes.

## Architecture

```
run.py                 # orchestration: universe → screen → console table → Excel
src/constants.py       # user config + fallback NASDAQ-100 list
src/universe.py        # Wikipedia constituents + market-cap ranking (caches .info)
src/screener.py        # the 5-point checklist engine
src/excel_export.py    # 3-sheet workbook writer
output/                # generated xlsx
```

`universe.py` fetches each ticker's `.info` once during ranking and hands the
cache to `screener.py`, so the market-data fetch isn't repeated.

## Output Workbook

| Sheet | Contents |
|-------|----------|
| Screener Results | Every ticker — raw metrics, per-check marks, score, signal |
| Shortlist | Score ≥ 4 only, sorted by score |
| Data Quality | Tickers with missing fields or fetch errors |

## Resilience

- Wikipedia constituent fetch falls back to a hardcoded list in `constants.py`.
- Any missing yfinance field marks the relevant check N/A rather than crashing.
- Per-ticker failures are recorded in the Data Quality sheet; the run continues.
