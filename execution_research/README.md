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
python test.py                      # 39 checks (controlled markets + real-data invariants)
```

Data: the gitignored `SET50_*.csv` files in `../order_execution/` (long format,
`TICKER, DATE, OPEN/HIGH/LOW/CLOSE_PRC, TRADING_VALUE, TRADING_VOLUME`).

## Design

| Piece | Choice |
|---|---|
| Universe | **10 names locked** for the whole backtest: KBANK, CPALL, ADVANC, PTTEP, AOT, BBL, SCB, PTT, KTB, BDMS (full history, no unadjusted corporate-action jumps) |
| Bars | 10, 11, 12, 13, 14, 15, 16, 17 → 8 per day; stray off-hours rows dropped. A 14:00 bar missing from the data (~30 % of days, all of 2023) is inserted with zero traded value — nothing fills there and it is never a decision bar |
| Period | from the first day with a 20-day ADV and a 21-day VWAP profile (2023-02-01) to 2026-11-19 ≈ 3.8 years |
| Parent orders | 2,000 random (decision bar, ticker, side) draws × 4 sizes = 1 / 5 / 10 / 25 % of **NAV 100M** → 8,000 orders; every algo executes the same set (paired) |
| Timeline | decision + arrival at Close_t; children in bars t+1 … t+8 (horizon = 1 day) |
| MARKET | everything in bar t+1, no cap |
| TWAP | cumulative target Q·(k+1)/8, ≤ 25 % of each bar's traded value, catch-up after a short bar |
| VWAP | cumulative target from a **rolling 21-day volume profile** (hourly share of daily value, pooled over the 10 names, known at the decision day's open; a day missing only 14:00 still counts, with 14:00 = 0 %), same cap/catch-up |
| POV10 / POV5 / POV5/10 | 10 % / 5 % / 5 % morning (bars 10–13) + 10 % afternoon (bars 14–17) of each bar's actual traded value; split at the SET lunch break |
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

At 25 % NAV (≈ 1.9 % of ADV): MARKET 76.7 bps, POV10 55.8, POV5/10 54.6, TWAP 53.7,
POV5 51.8, **VWAP 51.5**. MARKET vs VWAP = 25.1 bps (95 % CI 21.5–28.6). VWAP beats TWAP
at every size (TWAP pays for its 1/8 slice in the thin 14:00 bar). VWAP vs POV5 is not
significant at any size, and POV5 is far less risky (IS std 49–61 vs ≈ 89 bps) but
leaves ~6 % of the largest orders unfilled; splitting POV by session (5/10) never beat
POV5. See the notebook's section 10 for the full findings and limitations.
