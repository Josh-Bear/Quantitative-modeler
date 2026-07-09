# FRONTEND_REDESIGN.md
# Black-Litterman Optimizer — React Frontend Spec

> **For Claude Code:** Read this file completely before writing a single line of code.
> Implement exactly as specified. Do not add features not listed here.
> Do not modify anything in `backend/` unless explicitly stated.

---

## 0. Context & Goal

The current frontend is a single-page Vanilla JS app:
- `index.html` — all HTML for every page combined
- `app.js` — 43 KB, all logic combined, global `state = {}` object

**Goal:** Replace it with a React + Vite + TypeScript app in `frontend/src/`.
The FastAPI backend on `:8000` is **unchanged**. All existing API endpoints still work.
The BL math engine (`engine/matrix.js`, `engine/stats.js`, `engine/blacklitterman.js`) is kept as-is.

---

## 1. Tech Stack — Exact Versions

| Layer | Package | Version |
|---|---|---|
| Build | Vite | `^5` |
| UI | React | `^18` |
| Types | TypeScript | `^5` |
| Routing | react-router-dom | `^6` |
| State | zustand | `^4` |
| HTTP | native `fetch` (no axios) | — |
| Style | single `style.css` (copy from existing) | — |
| Charts | native Canvas (copy logic from existing app.js) | — |

No other libraries. No Tailwind. No UI kit.

---

## 2. File Structure — Create Exactly This

```
black_litterman_model/
  frontend/                     ← NEW (React Vite app root)
    package.json
    vite.config.ts
    tsconfig.json
    index.html                  ← Vite entry (minimal, just mounts #root)
    src/
      main.tsx                  ← ReactDOM.createRoot, Router wrapper
      App.tsx                   ← <Routes> definition + <Navbar>
      style.css                 ← copy from black_litterman_model/style.css verbatim
      types.ts                  ← ALL shared TypeScript interfaces (see §4)
      api/
        client.ts               ← all fetch() calls (see §5)
      store/
        marketStore.ts          ← Zustand slice (see §6.1)
        viewsStore.ts           ← Zustand slice (see §6.2)
        resultsStore.ts         ← Zustand slice (see §6.3)
      engine/
        index.ts                ← loads matrix.js, stats.js, blacklitterman.js via script tags or dynamic import; exposes typed wrappers
      pages/
        Setup.tsx               ← page 1 (see §7.1)
        ManualViews.tsx         ← page 2 (see §7.2)
        MLViews.tsx             ← page 3 (see §7.3)
        Results.tsx             ← page 4 (see §7.4)
      components/
        Navbar.tsx              ← top nav with 4 tabs
        ChipInput.tsx           ← ticker autocomplete + chips
        SliderRow.tsx           ← label + range + output
        ViewCard.tsx            ← single view editor (used in ManualViews)
        PreviewTable.tsx        ← data preview table (used in Setup)
        WeightChart.tsx         ← horizontal bar chart (used in Results)
        FrontierChart.tsx       ← canvas efficient frontier (used in Results)
  backend/                      ← DO NOT TOUCH
  engine/                       ← DO NOT TOUCH (matrix.js, stats.js, blacklitterman.js)
  style.css                     ← keep (will be copied to frontend/src/)
  docker-compose.yml            ← UPDATE frontend service only (see §9)
```

---

## 3. Routing — react-router-dom v6

```
/          → redirect to /setup
/setup     → <Setup />
/views     → <ManualViews />
/ml-views  → <MLViews />
/results   → <Results />
```

`<Navbar>` is rendered outside `<Routes>` so it appears on every page.
Active tab highlighted based on `useLocation().pathname`.

---

## 4. TypeScript Types — `src/types.ts`

Define all interfaces here. Import from here everywhere else.

```typescript
export interface Params {
  delta: number   // 1–10, step 0.1, default 3.0
  tau: number     // 0.01–0.2, step 0.01, default 0.05
  period: number  // 1–5 (years), step 1, default 3
  rf: number      // 0–10 (%), step 0.25, default 4.5
  minW: number    // 0–20 (%), step 1, default 5
  maxW: number    // 5–100 (%), step 5, default 10
}

export interface PriceSeries { date: string; close: number }

export interface MarketData {
  tickers: string[]
  dates: string[]
  prices: Record<string, PriceSeries[]>
  marketCap: Record<string, number>
  meta: Record<string, { name: string; sector: string }>
  wMkt: number[]      // market-cap weights, aligned to tickers order
  sigma: number[][]   // annualised covariance matrix
  signals: Record<string, { momentum: number; meanRev: number; relStrength: number }>
}

export type ViewType = 'absolute' | 'relative'

export interface View {
  id: number
  enabled: boolean
  type: ViewType
  picks: Record<string, number>   // ticker → weight (+1, -1, or 0)
  q: number                       // expected return (annualised)
  omega: number                   // view uncertainty variance
  mlGenerated: false              // always false for manual views
}

export interface MLView extends Omit<View, 'mlGenerated'> {
  mlGenerated: true
  rHat: number      // raw SVR prediction (63-day, before annualisation)
}

export type OmegaMode = 'he-litterman' | 'svr-residual' | 'blend'
export type MLStatus = 'idle' | 'loading' | 'done' | 'error'

export interface MLConfig {
  epochs: number      // 10–500, step 10, default 250
  omegaMode: OmegaMode
}

export interface MLResult {
  stock_order: string[]
  P: number[][]
  Q: number[]
  omega: Record<OmegaMode, number[]>
  n_absolute: number
  n_relative: number
  r_hats: Record<string, number>
  errors: Record<string, string>
}

export interface BLOutput {
  pi: number[]
  muBL: number[]
  sigmaBL: number[][]
  M: number[][]
}

export interface BLResult {
  tickers: string[]
  wMkt: number[]
  wStar: number[]    // constrained optimal weights
  wRaw: number[]     // unconstrained
  pi: number[]
  muBL: number[]
  metrics: {
    expReturn: number
    vol: number
    sharpe: number
    leverage: number
  }
  warnings: string[]
}

export interface Port {
  id: string
  name: string
  tickers: string[]
  last_run: string | null
  weights?: Record<string, number>
  metrics?: Partial<BLResult['metrics']>
}

export interface SearchResult {
  symbol: string
  name: string
  exchange: string
  type: string
}
```

---

## 5. API Client — `src/api/client.ts`

Base URL constant at top: `const API = 'http://localhost:8000'`

Export one object `api` with these methods. Each method throws on non-ok response.

```typescript
export const api = {
  // GET /api/data?tickers=A,B&period=3y
  fetchMarket(tickers: string[], period: string): Promise<{ prices, marketCap, meta, errors }>

  // GET /api/search?q=apple
  search(q: string): Promise<SearchResult[]>

  // POST /api/ml-views  body: { tickers, tau, delta, epochs }
  mlViews(tickers: string[], tau: number, delta: number, epochs: number): Promise<MLResult>

  // GET /api/ports
  getPorts(): Promise<Port[]>

  // POST /api/ports  body: { name, tickers }
  createPort(name: string, tickers: string[]): Promise<Port>

  // PUT /api/ports/:id  body: Partial<Port>
  updatePort(id: string, data: Partial<Port>): Promise<Port>

  // DELETE /api/ports/:id
  deletePort(id: string): Promise<void>
}
```

---

## 6. Zustand Stores

### 6.1 `src/store/marketStore.ts`

```typescript
interface MarketStore {
  tickers: string[]
  params: Params
  market: MarketData | null

  // actions
  addTicker: (t: string) => void
  removeTicker: (t: string) => void
  setParams: (p: Partial<Params>) => void
  setMarket: (m: MarketData | null) => void
}
```

Default params: `{ delta:3.0, tau:0.05, period:3, rf:4.5, minW:5, maxW:10 }`
Default tickers: `['AAPL', 'MSFT', 'GOOGL', 'NVDA']`

### 6.2 `src/store/viewsStore.ts`

```typescript
interface ViewsStore {
  manualViews: View[]
  mlViews: MLView[]
  mlConfig: MLConfig
  mlStatus: MLStatus
  mlError: string | null
  nextId: number

  // manual view actions
  addView: (v: Omit<View, 'id'>) => void
  updateView: (id: number, patch: Partial<View>) => void
  removeView: (id: number) => void

  // manual view bulk action
  clearManualViews: () => void

  // ML view actions
  setMLViews: (views: MLView[]) => void
  clearMLViews: () => void
  setMLConfig: (c: Partial<MLConfig>) => void
  setMLStatus: (s: MLStatus, error?: string) => void

  // computed: returns [...manualViews, ...mlViews] filtered to enabled only
  activeViews: () => (View | MLView)[]
}
```

Default mlConfig: `{ epochs: 250, omegaMode: 'he-litterman' }`

### 6.3 `src/store/resultsStore.ts`

```typescript
interface ResultsStore {
  result: BLResult | null
  ports: Port[]

  setResult: (r: BLResult | null) => void
  setPorts: (p: Port[]) => void
  addPort: (p: Port) => void
  removePort: (id: string) => void
}
```

---

## 7. Pages

### 7.1 `src/pages/Setup.tsx`

**Sections (top to bottom):**

1. **Stock Selector card**
   - `<ChipInput>` — autocomplete calls `api.search(q)`, picks add to `marketStore.tickers`
   - Existing ticker chips with × remove button

2. **Ports card** (below Stock Selector)
   - Load ports from `api.getPorts()` on mount → store in `resultsStore.ports`
   - Each port shows: name, ticker count, click to load tickers
   - "Save as Port" button → `api.createPort(prompt('name'), tickers)`

3. **Parameters card**
   - 6 `<SliderRow>` components for δ, τ, period, rf, minW, maxW
   - Values bound to `marketStore.params`
   - "📡 ดึงข้อมูลตลาด" button

4. **Data Preview card**
   - `<PreviewTable>` — shows ticker, name, marketCap, w_mkt, annual vol, momentum, status
   - Only renders if `marketStore.market !== null`

**"ดึงข้อมูลตลาด" button logic:**
```
1. call api.fetchMarket(tickers, `${period}y`)
2. run Stats.alignPrices(data.prices) — import Stats from engine/
3. compute sigma, wMkt, signals via Stats functions
4. call marketStore.setMarket(market)
5. show error status if any ticker failed
```

---

### 7.2 `src/pages/ManualViews.tsx`

**Sections:**

1. **Auto Signal Generator card**
   - Checkboxes: Momentum, Mean-Reversion, Relative Strength
   - "⚡ Generate Auto Views" button
   - Logic: same as current `gen-auto` handler in app.js — reads `market.signals`, creates View objects, calls `viewsStore.addView()`

2. **Manual View Builder card**
   - "＋ เพิ่ม View" → `viewsStore.addView(blankView())`
   - List of `<ViewCard>` one per `viewsStore.manualViews`

3. **View Summary table**
   - Shows all manualViews: #, type, picks, Q, Ω, enabled toggle

4. **Action bar**
   - "↺ Reset to Market" → calls `viewsStore.clearManualViews()`
   - "🧮 คำนวณ Black-Litterman →" → runs BL compute (logic below), stores result, navigates to `/results`

**BL compute logic** — implement inside `ManualViews.tsx` in the button onClick handler:
```typescript
// 1. collect all active views (manual + ML) from viewsStore.activeViews()
// 2. filter: skip views where all picks are 0 or |q| < 0.001
// 3. if any active views: build P (K×N), Q (K), omega (K) arrays
// 4. call BL.compute({ delta, tau, sigma, wMkt, P, Q, omega })
// 5. call BL.optimalWeights(delta, out.sigmaBL, out.muBL) → wRaw
// 6. call BL.constrainWeights(wRaw, { longOnly: true, minW: minW/100, maxW: maxW/100 }) → wStar
// 7. compute metrics: expReturn, vol, sharpe (BL.portfolioReturn/Vol/sharpe), leverage (BL.leverage)
// 8. call resultsStore.setResult({ tickers, wMkt, wStar, wRaw, pi, muBL, metrics, warnings: [] })
// 9. navigate('/results')
```

**`<ViewCard>` props:** `view: View, onChange: (patch) => void, onRemove: () => void`
- Toggle enabled checkbox
- Type select (absolute / relative)
- Per-ticker weight inputs (one per ticker in market)
- Q number input
- Confidence/Ω select (maps Thai labels → omega values, same as current CONFIDENCE object)

---

### 7.3 `src/pages/MLViews.tsx`

**This is the NEW dedicated page for ML views.**

**Sections:**

1. **Config card**
   - `<SliderRow>` for epochs: min=10, max=500, step=10, default=250
   - Select for Ω mode: He-Litterman / SVR Residual / Blend
   - Both bound to `viewsStore.mlConfig`

2. **Generate card**
   - "🤖 Generate ML Views" button
   - Calls `api.mlViews(market.tickers, tau, delta, epochs)`
   - Shows loading spinner + "Training LSTM+SVR... (may take 1–5 min)"
   - On success: calls `viewsStore.setMLViews(parseMLViews(result, omegaMode))`
   - Shows: "✅ N absolute + M relative views" or error message
   - Requires `market !== null`, shows warning otherwise

3. **r̂ per stock table** (shown after successful generation)
   - Columns: Ticker | Sector | r̂ (annualised %) | Ω | Direction
   - Direction: ▲ green if r̂ > 0, ▼ red if < 0
   - Sorted by r̂ descending

4. **ML Views list**
   - Shows current `viewsStore.mlViews`
   - Each row: type (absolute/relative), picks, Q, Ω, enable toggle
   - "🗑 Clear all ML views" button → `viewsStore.clearMLViews()`

**`parseMLViews` function** (same logic as in app.js, adapted to TypeScript):
```typescript
const ML_Q_CLAMP = 0.30

function parseMLViews(result: MLResult, omegaMode: OmegaMode): MLView[] {
  // same P/Q/omega extraction as app.js parseMLViews
  // tag each view with mlGenerated: true and rHat
}
```

---

### 7.4 `src/pages/Results.tsx`

**Sections:**

1. **Metrics row** — 4 cards: Expected Return, Volatility, Sharpe, Leverage
2. **Warnings** — yellow banner if leverage > 1.5 or any constraint warnings
3. **Weight Comparison card** — `<WeightChart>` + table (w_mkt, w*, Δ)
4. **Returns card** — table (Π prior, μ_BL, Δ)
5. **Efficient Frontier card** — `<FrontierChart>` canvas (same logic as current)
6. **Action bar** — Export CSV, Copy Summary, Save to Port

If `resultsStore.result === null`: show empty state card with message "ยังไม่มีผลลัพธ์" and a button "← กลับไปหน้า Views" that navigates to `/views`.

The BL compute logic lives in `ManualViews.tsx` (see §7.2 action bar). Results.tsx is display-only — it reads from `resultsStore.result` and renders.

---

## 8. BL Engine Wrapper — `src/engine/index.ts`

The existing JS files in `engine/` use `window.Matrix`, `window.Stats`, `window.BL`.

**Step 1:** Copy the three files into `frontend/public/engine/`:
```
frontend/public/engine/matrix.js         ← copy from ../engine/matrix.js
frontend/public/engine/stats.js          ← copy from ../engine/stats.js
frontend/public/engine/blacklitterman.js ← copy from ../engine/blacklitterman.js
```
Vite serves `frontend/public/` at `/` so they will be reachable as `/engine/matrix.js`.

**Step 2:** Add `<script>` tags in `frontend/index.html` BEFORE `<script type="module" src="/src/main.tsx">`:
```html
<!-- frontend/index.html -->
<script src="/engine/matrix.js"></script>
<script src="/engine/stats.js"></script>
<script src="/engine/blacklitterman.js"></script>
<script type="module" src="/src/main.tsx"></script>
```

**Step 3:** `src/engine/index.ts` — typed wrappers:
```typescript
declare global {
  const Matrix: any
  const Stats: any
  const BL: any
}
export { Matrix, Stats, BL }
```

**Important:** Do NOT import the engine files as ES modules. They use `window.X` assignment and must be loaded as plain scripts first.

---

## 9. Docker — Update `docker-compose.yml`

Replace the existing `frontend` service with:

```yaml
frontend:
  build:
    context: ./frontend
    dockerfile: Dockerfile
  restart: unless-stopped
  volumes:
    - ./frontend/src:/app/src        # HMR in dev
    - ./style.css:/app/src/style.css # sync root style.css
  ports:
    - "8770:5173"   # Vite dev server
  depends_on:
    - backend
```

Create `frontend/Dockerfile`:
```dockerfile
FROM node:20-alpine
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
```

---

## 10. Constants to Preserve Exactly

These values must match the existing app.js exactly:

```typescript
// src/pages/ManualViews.tsx
const CONFIDENCE: Record<string, number> = {
  'สูงมาก':  0.0002,
  'สูง':     0.0005,
  'ปานกลาง': 0.0010,
  'ต่ำ':     0.0020,
  'ต่ำมาก':   0.0050,
}
const Q_FLOOR = 0.03
const Q_CAP   = 0.15

// src/pages/MLViews.tsx
const ML_Q_CLAMP = 0.30

// src/api/client.ts
const API_BASE = 'http://localhost:8000'
```

---

## 11. What NOT to Change

- Do NOT modify `backend/` (any file)
- Do NOT modify `engine/matrix.js`, `engine/stats.js`, `engine/blacklitterman.js`
- Do NOT modify `backend/ml_constants.py`
- Do NOT add libraries beyond what is listed in §1
- Do NOT add `localStorage` (not supported in this environment)
- Do NOT create a separate `README.md`

---

## 12. Definition of Done

- [ ] `cd frontend && npm install && npm run dev` starts on port 5173
- [ ] All 4 pages load without console errors
- [ ] Setup page: can add tickers, adjust sliders, fetch market data, see preview table
- [ ] ManualViews page: can add/edit/remove views, generate auto views, run BL → navigate to results
- [ ] MLViews page: can configure epochs + omega mode, click generate, see r̂ table and ML views list
- [ ] Results page: shows weight table, return table, efficient frontier canvas
- [ ] `docker compose up --build` starts all 3 services
