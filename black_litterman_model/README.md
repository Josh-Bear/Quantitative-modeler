# Black-Litterman Portfolio Optimizer

Interactive web app that fetches live market data, blends the market-implied
(equilibrium) returns with your own **views**, and produces optimal portfolio
weights via the Black-Litterman model.

Built as a **vanilla-JS frontend + Python stdlib proxy server** (same pattern as
`../dcf/` — no build step, no npm, no Flask). The plan in
`BL_Optimizer_Plan.md` specced React/Vite; this implementation keeps the repo's
zero-dependency convention while delivering every feature in the plan.

## Running

```bash
cd black_litterman_model
pip install yfinance
python server.py
# open http://localhost:8770
```

The backend (`server.py`) only proxies Yahoo Finance — it fetches monthly
adjusted closes (default 3yr) + market cap per ticker, which solves the CORS
problem noted in the plan. **All BL math runs client-side** in `engine/`.

## Workflow (3 tabs)

1. **Setup** — pick tickers (or a preset: Tech / Finance / Energy / Mixed / Thai),
   set δ (risk aversion) and τ (prior uncertainty), then fetch data. The preview
   table shows market cap, w_mkt, annualised vol and momentum.
2. **Views** — generate views automatically from 3 signals (Momentum,
   Mean-Reversion, Relative Strength) and/or build manual Absolute/Relative views
   with a pick vector, expected return Q, and confidence Ω.
3. **Results** — weight comparison (table + bar chart), prior vs posterior
   returns, efficient-frontier scatter (Market / BL Optimal / Max Sharpe), risk
   metrics (Expected Return, Vol, Sharpe, Tracking Error), and CSV / clipboard
   export.

## Architecture

```
server.py                  # stdlib HTTP server; /api/data proxies yfinance
index.html / style.css     # UI shell, 3-tab single page
app.js                     # state, navigation, data wiring, charts, export
engine/
  matrix.js                # inverse (Gauss-Jordan), multiply, transpose, …
  stats.js                 # returns, annualised covariance, market weights, signals
  blacklitterman.js        # BL core + portfolio analytics + frontier sampler
```

`engine/` has no dependencies and no DOM access, so it is unit-testable in Node.

## The math

```
Prior:          Π    = δ · Σ · w_mkt
Posterior Var:  M    = [(τΣ)⁻¹ + Pᵀ Ω⁻¹ P]⁻¹
Posterior Mean: μ_BL = M · [(τΣ)⁻¹ Π + Pᵀ Ω⁻¹ Q]
Total Cov:      Σ_BL = Σ + M
Optimal Weight: w*   = (δ · Σ_BL)⁻¹ · μ_BL    (normalised to sum to 1)
```

Covariance and returns are **annualised** (×12) so Π, μ_BL and the metrics read
in annual terms. Σ is regularised (+1e-4 on the diagonal) before inversion so a
near-singular covariance matrix from highly-correlated names doesn't blow up.

### Risk controls (constrained portfolio)

The raw `w* = (δΣ_BL)⁻¹μ_BL` is the *unconstrained* optimum and can be wildly
short / concentrated. Before display it passes through `constrainWeights()`:

- **Long-only** — negative weights clamped to 0.
- **Per-stock cap / floor** — `MAX_WEIGHT = 40%`, `MIN_WEIGHT = 5%`, enforced by
  iterative water-filling (cap excess and redistribute, floor deficit and pull
  from the rest), bounds auto-relaxed if infeasible for the stock count.

Auto-generated view returns are clamped to `[3%, 15%]` so a runaway momentum
signal can't push μ_BL to absurd levels. **Sharpe** nets out a 5% risk-free
rate; **Tracking Error** is colour-coded (✓ ≤5%, • 5–10%, ⚠ >10%); a **leverage
indicator** flags when the pre-constraint solution wanted heavy shorts. See
`BL_BugFix_Plan.md` for the full list.

## Verification

The JS engine reproduces `test.py` (the original 4-Thai-stock proof of concept)
to the basis point: `w* = [PTT 53.36%, AOT 27.98%, KBANK 8.20%, CPF 10.45%]`.
Sanity check: with **no views**, `w*` collapses exactly back to `w_mkt`.
