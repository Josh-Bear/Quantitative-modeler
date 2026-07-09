/**
 * Loads the plain-JS engine files (matrix.js → stats.js → blacklitterman.js)
 * into a Node/vitest environment using the Function constructor, since the
 * files are written as IIFEs assigned to `const` globals (no ES-module exports).
 */
import { readFileSync } from 'fs'
import { resolve, dirname } from 'path'
import { fileURLToPath } from 'url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const ENGINE = resolve(__dirname, '../../../engine')

// Explicit file → exported global name mapping
const GLOBAL_NAME: Record<string, string> = {
  'matrix.js':         'Matrix',
  'stats.js':          'Stats',
  'blacklitterman.js': 'BL',
}

function load(file: string, ...deps: unknown[]): unknown {
  const src = readFileSync(resolve(ENGINE, file), 'utf-8')
  const globalName = GLOBAL_NAME[file]
  if (!globalName) throw new Error(`Unknown engine file: ${file}`)
  const paramNames = deps.map((_, i) => ['Matrix', 'Stats'][i])
  // eslint-disable-next-line no-new-func
  const fn = new Function(...paramNames, src + `;\nreturn ${globalName};`)
  return fn(...deps)
}

// Load in dependency order
export const Matrix = load('matrix.js') as {
  zeros: (r: number, c: number) => number[][]
  identity: (n: number) => number[][]
  transpose: (A: number[][]) => number[][]
  multiply: (A: number[][], B: number[][]) => number[][]
  matVec: (A: number[][], v: number[]) => number[]
  scale: (A: number[][], s: number) => number[][]
  add: (A: number[][], B: number[][]) => number[][]
  diag: (v: number[]) => number[][]
  inverse: (A: number[][]) => number[][]
  regularize: (A: number[][], eps: number) => number[][]
  quadForm: (w: number[], A: number[][]) => number
  dot: (a: number[], b: number[]) => number
}

export const Stats = load('stats.js', Matrix) as {
  alignPrices: (p: Record<string, { date: string; close: number }[]>) => { dates: string[]; prices: Record<string, number[]> }
  returns: (s: number[]) => number[]
  returnsMatrix: (prices: Record<string, number[]>, tickers: string[]) => number[][]
  covariance: (R: number[][]) => number[][]
  marketWeights: (cap: Record<string, number>, tickers: string[]) => number[]
  equalWeights: (n: number) => number[]
  annualVol: (R: number[][], j: number) => number
  momentum: (prices: Record<string, number[]>, tickers: string[]) => number[]
  relativeStrength: (prices: Record<string, number[]>, tickers: string[]) => number[]
  zScore: (prices: Record<string, number[]>, tickers: string[]) => number[]
}

export const BL = load('blacklitterman.js', Matrix) as {
  impliedReturns: (delta: number, sigma: number[][], wMkt: number[]) => number[]
  compute: (args: {
    delta: number; tau: number; sigma: number[][];
    wMkt: number[]; P?: number[][] | null; Q?: number[] | null; omega?: number[] | null
  }) => { pi: number[]; muBL: number[]; sigmaBL: number[][] }
  optimalWeights: (delta: number, sigmaBL: number[][], muBL: number[]) => number[]
  constrainWeights: (w: number[], opts?: { longOnly?: boolean; minW?: number; maxW?: number }) => number[]
  leverage: (w: number[]) => number
  portfolioReturn: (w: number[], mu: number[]) => number
  portfolioVol: (w: number[], sigma: number[][]) => number
  sharpe: (w: number[], mu: number[][], sigma: number[][], rf?: number) => number
}
