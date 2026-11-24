// All shared TypeScript interfaces (docs/FRONTEND_REDESIGN.md §4).
// Import from here everywhere else.

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

// One row per requested ticker — `sector` and the training/MSE fields are
// absent when the ticker never got past the fetch stage (see `success`/`error`).
export interface MLDiagnostic {
  ticker: string
  sector?: string
  n_rows: number
  n_train?: number
  n_val?: number
  lstm_val_mse?: number
  svr_train_mse?: number
  svr_test_mse?: number
  r_hat?: number
  r_hat_raw?: number   // pre-shrink raw 63-day prediction
  shrink_beta?: number // cross-sectional shrink weight β ∈ (0,1]; low = damped hard
  omega?: number
  success: boolean
  error?: string | null
}

export interface MLResult {
  stock_order: string[]
  P: number[][]
  Q: number[]
  omega: Record<OmegaMode, number[]>
  n_absolute: number
  n_relative: number
  sectors: Record<string, string>
  r_hats: Record<string, number>
  errors: Record<string, string>
  diagnostics: MLDiagnostic[]
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

export interface PortLastRun {
  date: string
  delta: number
  tau: number
  weights: Record<string, number>
  metrics: Partial<BLResult['metrics']>
}

export interface Port {
  id: string
  name: string
  tickers: string[]
  last_run: PortLastRun | null
}

export interface SearchResult {
  symbol: string
  name: string
  exchange: string
  type: string
}
