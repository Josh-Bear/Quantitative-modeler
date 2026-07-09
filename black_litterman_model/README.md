# Black-Litterman Portfolio Optimizer

Interactive web app that fetches live market data, blends the market-implied
(equilibrium) returns with your own **views**, and produces optimal portfolio
weights via the Black-Litterman model.

There are **two frontend implementations** in this directory — pick one:

| | Legacy vanilla-JS | New React (`frontend/`) |
|---|---|---|
| Stack | plain `index.html` + `app.js`, no build step | Vite + React + TypeScript, `npm run dev` |
| Serves on | `:8770` (via `python server.py`) | `:5173` directly, or `:8770` via `docker compose` |
| Needs `backend/` (FastAPI, `:8000`) for | Ports, 🤖 ML Views | Ports, ML Views (dedicated page) |
| Status | original implementation, fully featured | ports the same features per `docs/FRONTEND_REDESIGN.md` |

**Both talk to the same `backend/` FastAPI service for Ports and ML Views — run
it once (`cd backend && uvicorn main:app --reload --port 8000`, needs MongoDB)
regardless of which frontend you use.** Only run ONE of the two frontends at a
time if you're using `docker compose up`, since its `frontend` service maps
container port 5173 → host port **8770**, the same port `python server.py`
binds to directly — running both simultaneously will conflict on `:8770`.

## Running (legacy vanilla-JS)

```bash
cd black_litterman_model
pip install yfinance
python server.py
# open http://localhost:8770
```

The backend (`server.py`) only proxies Yahoo Finance — it fetches monthly
adjusted closes (default 3yr) + market cap per ticker, which solves the CORS
problem noted in `docs/BL_Optimizer_Plan.md`. **All BL math runs client-side**
in `engine/`. Ports and 🤖 ML Views additionally require `backend/` running on
`:8000` (see below).

## Running (new React frontend)

```bash
cd black_litterman_model/backend
cp ../.env.example ../.env   # first time only
uvicorn main:app --reload --port 8000   # needs MongoDB for Ports

cd ../frontend
npm install
npm run dev
# open http://localhost:5173
```

`.env.example`'s `CORS_ORIGINS` already allows both `:8770` (legacy/docker) and
`:5173` (Vite dev server) so either frontend can call the backend without a CORS error.

## Workflow (4 tabs)

1. **Setup** — pick tickers (autocomplete search, or load a saved Port), set
   δ (risk aversion), τ (prior uncertainty), history window, risk-free rate and
   min/max weight, then fetch data. The preview table shows market cap, w_mkt,
   annualised vol and momentum. "Save as Port" persists the current tickers via
   `backend/` → MongoDB.
2. **ML Model** *(legacy app only — folded into the "ML Views" tab in the React
   app)* — train the LSTM+SVR pipeline and inspect per-stock diagnostics: rows
   fetched, LSTM validation MSE, SVR train/test MSE, r̂ and ω.
3. **Views** — generate views automatically from 3 signals (Momentum,
   Mean-Reversion, Relative Strength), build manual Absolute/Relative views
   with a pick vector, expected return Q and confidence Ω, and/or pull in
   🤖 ML Views (LSTM+SVR-generated views, see `docs/ML_VIEWS_DESIGN.md`).
4. **Results** — weight comparison (table + bar chart), prior vs posterior
   returns, efficient-frontier scatter (Market / BL Optimal / Max Sharpe), risk
   metrics (Expected Return, Vol, Sharpe, Leverage), and CSV / clipboard /
   Save-to-Port export.

## Architecture

```
server.py                  # stdlib HTTP server; /api/data proxies yfinance (legacy)
index.html / style.css     # legacy UI shell, 4-tab single page
app.js                     # legacy state, navigation, data wiring, charts, export
engine/
  matrix.js                # inverse (Gauss-Jordan), multiply, transpose, …
  stats.js                 # returns, annualised covariance, market weights, signals
  blacklitterman.js        # BL core + portfolio analytics + frontier sampler
backend/                   # FastAPI (:8000) — market/search/ports/ml-views routers + MongoDB
frontend/                  # React + Vite + TypeScript app (see docs/FRONTEND_REDESIGN.md)
```

`engine/` has no dependencies and no DOM access, so it is unit-testable in Node.
Both frontends load it as classic `<script>` tags. The root `engine/` and root
`style.css` are the **single source of truth** — the copies the React app needs
(`frontend/public/engine/`, `frontend/src/style.css`) are generated, gitignored
artifacts: `npm run dev` / `npm run build` regenerate them automatically (via the
`sync` script), and `docker compose` bind-mounts the root originals directly.

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
`docs/BL_BugFix_Plan.md` for the full list.

## Verification

The JS engine reproduces `test.py` (the original 4-Thai-stock proof of concept)
to the basis point: `w* = [PTT 53.36%, AOT 27.98%, KBANK 8.20%, CPF 10.45%]`.
Sanity check: with **no views**, `w*` collapses exactly back to `w_mkt`.
