# execution_research — which execution algorithm is cheapest on SET50?

A controlled experiment comparing **MARKET, TWAP, VWAP and POV** on the *same*
parent orders, using real hourly SET50 bars (2023-01 → 2026-11). The main
deliverable is **`Research.ipynb`**: research question → data → cost model →
experiment design → results → statistics → sensitivity → conclusions.

## Run

```bash
pip install -r requirements.txt
jupyter notebook Research.ipynb     # the study, with charts and conclusions (~15 s to execute)
python run.py                       # same experiment, text report + CSVs → output/
python run.py --quick               # smoke test
python test.py                      # 31 checks (controlled markets + real-data invariants)
```

Data: the gitignored `SET50_*.csv` files in `../order_execution/` (long format,
`TICKER, DATE, OPEN/HIGH/LOW/CLOSE_PRC, TRADING_VALUE, TRADING_VOLUME`).

## Design

| Piece | Choice |
|---|---|
| Bars | 10, 11, 12, 13, 15, 16, 17 → 7 per day (14:00 and stray off-hours rows dropped) |
| Universe | point-in-time **Top 10 by trailing 20-day traded value** (no look-ahead) |
| Sample split | 2023–24 in-sample (VWAP volume profile only) · 2025–26 out-of-sample (orders) |
| Parent orders | 2,000 random (decision bar, ticker, side) draws × 4 sizes = 1 / 5 / 10 / 25 % of **NAV 100M** → 8,000 orders; every algo executes the same set (paired) |
| Jump filter | an order is redrawn if its window has an \|hourly return\| > 15 % (prices are not corporate-action adjusted) |
| Timeline | decision + arrival at Close_t; children in bars t+1 … t+7 (horizon = 1 day) |
| MARKET | everything in bar t+1, no cap |
| TWAP / VWAP | cumulative target (equal / in-sample volume profile), ≤ 25 % of each bar's traded value, catch-up after a short bar |
| POV | 10 % of each bar's actual traded value |
| Fill price | bar VWAP (value / volume, clipped to [low, high]) ± (½ spread + impact) |
| Costs | ½ × 1 tick spread (assumption), impact = σ_hour × √(child / bar value) × price, commission 0.157 % + VAT |
| Metric | Implementation Shortfall vs arrival = timing + spread + impact + commission + opportunity; fill vs interval VWAP |
| Statistics | paired t-test (Holm-adjusted) + Wilcoxon + bootstrap CI on order-level differences |
| Robustness | one-at-a-time sensitivity (spread, impact Y, POV rate, cap) and an in-sample re-run |

## Layout

```
Research.ipynb        the study (calls src/, adds charts + conclusions)
run.py                same experiment → output/report.txt + CSVs
test.py               checks
src/constants.py      ALL parameters
src/data.py           bars → close/value/volume/vwap, σ, jumps, ADV, Top-N, volume profile
src/orders.py         parent-order generator (experiment design)
src/cost.py           tick table, spread, square-root impact, commission
src/engine.py         the four algorithms + execution loop + IS decomposition
src/stats.py          summary, paired tests, breakdowns, sensitivity
src/experiment.py     run_experiment() — the whole study in one call
src/plots.py          notebook charts
```

## Headline (seed in `constants.py`)

At 25 % NAV (≈ 1.4 % of ADV): MARKET 76.1 bps, POV 59.6, TWAP 54.5, **VWAP 53.2**.
MARKET vs VWAP gap = 22.9 bps (95 % CI 18.4–27.5); significant from 5 % NAV up, not
at 1 % NAV. TWAP/VWAP buy the lower cost with higher risk (IS std ≈ 127 vs 75–82 bps).
VWAP ranks first in every sensitivity setting and in the in-sample re-run. See the
notebook's section 10 for the full findings and limitations.
