# execution_research — which execution algorithm is cheapest on SET50?

A controlled experiment comparing **MARKET, TWAP, VWAP, POV10, POV5 and POV5/10**
on the *same* parent orders, using real hourly SET50 bars (Feb 2023 → Nov 2026).
The main deliverable is **`Research.ipynb`**: research question → data → cost model →
experiment design → results → statistics → sensitivity → conclusions.

## Run

```bash
pip install -r requirements.txt
jupyter notebook Research.ipynb     # the study, with charts and conclusions (~15 s to execute)
python run.py                       # same experiment, text report + CSVs → output/
python run.py --quick               # smoke test
python test.py                      # 36 checks (controlled markets + real-data invariants)
```

Data: the gitignored `SET50_*.csv` files in `../order_execution/` (long format,
`TICKER, DATE, OPEN/HIGH/LOW/CLOSE_PRC, TRADING_VALUE, TRADING_VOLUME`).

## Design

| Piece | Choice |
|---|---|
| Universe | **10 names locked** for the whole backtest: KBANK, CPALL, ADVANC, PTTEP, AOT, BBL, SCB, PTT, KTB, BDMS (full history, no unadjusted corporate-action jumps) |
| Bars | 10, 11, 12, 13, 15, 16, 17 → 7 per day (14:00 and stray off-hours rows dropped) |
| Period | from the first day with a 20-day ADV and a 21-day VWAP profile (2023-02-01) to 2026-11-19 ≈ 3.8 years |
| Parent orders | 2,000 random (decision bar, ticker, side) draws × 4 sizes = 1 / 5 / 10 / 25 % of **NAV 100M** → 8,000 orders; every algo executes the same set (paired) |
| Timeline | decision + arrival at Close_t; children in bars t+1 … t+7 (horizon = 1 day) |
| MARKET | everything in bar t+1, no cap |
| TWAP | cumulative target Q·(k+1)/7, ≤ 25 % of each bar's traded value, catch-up after a short bar |
| VWAP | cumulative target from a **rolling 21-day volume profile** (hourly share of daily value, pooled over the 10 names, known at the decision day's open), same cap/catch-up |
| POV10 / POV5 / POV5/10 | 10 % / 5 % / 5 % morning (bars 10–13) + 10 % afternoon (bars 15–17) of each bar's actual traded value; split at the SET lunch break |
| Fill price | bar VWAP (value / volume, clipped to [low, high]) ± (½ spread + impact) |
| Costs | ½ × 1 tick spread (assumption), impact = σ_hour × √(child / bar value) × price, commission 0.157 % + VAT |
| Metric | Implementation Shortfall vs arrival = timing + spread + impact + commission + opportunity; fill vs interval VWAP |
| Statistics | paired t-test (Holm-adjusted over 15 pairs) + Wilcoxon + bootstrap CI on order-level differences |
| Robustness | one-at-a-time sensitivity (spread, impact Y, cap) and results by year |

## Layout

```
Research.ipynb        the study (calls src/, adds charts + conclusions)
run.py                same experiment → output/report.txt + CSVs
test.py               checks
src/constants.py      ALL parameters (universe, sizes, POV schedules, costs, sensitivity grid)
src/data.py           bars → close/value/volume/vwap, σ, jumps, ADV, rolling VWAP profile
src/orders.py         parent-order generator (experiment design)
src/cost.py           tick table, spread, square-root impact, commission
src/engine.py         the six algorithms + execution loop + IS decomposition
src/stats.py          summary, paired tests, breakdowns, sensitivity
src/experiment.py     run_experiment() — the whole study in one call
src/plots.py          notebook charts
```

## Headline (seed in `constants.py`)

At 25 % NAV (≈ 1.9 % of ADV): MARKET 70.7 bps, POV10 56.2, POV5/10 54.3, POV5 51.7,
TWAP 49.0, **VWAP 47.9**. MARKET vs VWAP = 22.8 bps (95 % CI 19.6–26.0). TWAP/VWAP buy
the lower cost with higher risk (IS std ≈ 89–90 vs 55–66 bps for MARKET/POV). POV5 is
the cheapest POV but leaves ~6 % of the largest orders unfilled; splitting POV by
session (5/10) never beat POV5. VWAP ranks first in every sensitivity setting and in
every year for orders ≥ 5 % NAV. See the notebook's section 10 for the full findings
and limitations.
