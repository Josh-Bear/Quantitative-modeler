/**
 * Unit tests — BL engine
 * Covers: Matrix ops, Stats signals, BL posterior + constrainWeights
 */
import { describe, it, expect } from 'vitest'
import { Matrix, Stats, BL } from './loadEngine'

// ────────────────────────────────────────────
// Helpers
// ────────────────────────────────────────────
const close = (a: number, b: number, tol = 1e-9) => Math.abs(a - b) < tol
const sumClose = (arr: number[], target: number, tol = 1e-9) =>
  close(arr.reduce((s, x) => s + x, 0), target, tol)

// ────────────────────────────────────────────
// Matrix
// ────────────────────────────────────────────
describe('Matrix', () => {
  it('zeros — correct shape and all zeros', () => {
    const Z = Matrix.zeros(3, 2)
    expect(Z).toHaveLength(3)
    expect(Z[0]).toHaveLength(2)
    expect(Z.flat().every(x => x === 0)).toBe(true)
  })

  it('identity — diagonal ones, off-diagonal zeros', () => {
    const I = Matrix.identity(3)
    expect(I[0][0]).toBe(1)
    expect(I[1][1]).toBe(1)
    expect(I[2][2]).toBe(1)
    expect(I[0][1]).toBe(0)
    expect(I[1][0]).toBe(0)
  })

  it('transpose — rows become cols', () => {
    const A = [[1, 2, 3], [4, 5, 6]]
    const T = Matrix.transpose(A)
    expect(T).toHaveLength(3)
    expect(T[0]).toEqual([1, 4])
    expect(T[1]).toEqual([2, 5])
    expect(T[2]).toEqual([3, 6])
  })

  it('multiply — 2×2 identity is neutral', () => {
    const A = [[1, 2], [3, 4]]
    const I = Matrix.identity(2)
    const AI = Matrix.multiply(A, I)
    expect(AI[0]).toEqual([1, 2])
    expect(AI[1]).toEqual([3, 4])
  })

  it('multiply — simple 2×2 * 2×2', () => {
    // [[1,2],[3,4]] * [[5,6],[7,8]] = [[19,22],[43,50]]
    const A = [[1, 2], [3, 4]]
    const B = [[5, 6], [7, 8]]
    const C = Matrix.multiply(A, B)
    expect(C[0]).toEqual([19, 22])
    expect(C[1]).toEqual([43, 50])
  })

  it('multiply — throws on dimension mismatch', () => {
    const A = [[1, 2, 3]]
    const B = [[1, 2], [3, 4]]   // 2×2, but A has 3 cols
    expect(() => Matrix.multiply(A, B)).toThrow()
  })

  it('matVec — matrix × vector', () => {
    const A = [[1, 0], [0, 2]]
    const v = [3, 4]
    expect(Matrix.matVec(A, v)).toEqual([3, 8])
  })

  it('dot — dot product', () => {
    expect(Matrix.dot([1, 2, 3], [4, 5, 6])).toBe(32)
  })

  it('scale — multiplies all entries by scalar', () => {
    const A = [[1, 2], [3, 4]]
    const B = Matrix.scale(A, 2)
    expect(B[0]).toEqual([2, 4])
    expect(B[1]).toEqual([6, 8])
  })

  it('add — element-wise addition', () => {
    const A = [[1, 2], [3, 4]]
    const B = [[5, 6], [7, 8]]
    const C = Matrix.add(A, B)
    expect(C[0]).toEqual([6, 8])
    expect(C[1]).toEqual([10, 12])
  })

  it('inverse — I⁻¹ = I', () => {
    const I = Matrix.identity(3)
    const Inv = Matrix.inverse(I)
    for (let i = 0; i < 3; i++) {
      for (let j = 0; j < 3; j++) {
        expect(Inv[i][j]).toBeCloseTo(I[i][j], 10)
      }
    }
  })

  it('inverse — A * A⁻¹ ≈ I (2×2)', () => {
    const A = [[4, 7], [2, 6]]
    const Inv = Matrix.inverse(A)
    const prod = Matrix.multiply(A, Inv)
    expect(prod[0][0]).toBeCloseTo(1, 8)
    expect(prod[0][1]).toBeCloseTo(0, 8)
    expect(prod[1][0]).toBeCloseTo(0, 8)
    expect(prod[1][1]).toBeCloseTo(1, 8)
  })

  it('quadForm — wᵀ Σ w for diagonal Σ = variance', () => {
    // w=[0.5,0.5], Σ=diag([0.04,0.04]) => wᵀΣw = 0.04 * (0.25+0.25) = 0.02
    const w = [0.5, 0.5]
    const sigma = Matrix.diag([0.04, 0.04])
    expect(Matrix.quadForm(w, sigma)).toBeCloseTo(0.02, 10)
  })
})

// ────────────────────────────────────────────
// Stats
// ────────────────────────────────────────────
describe('Stats', () => {
  it('returns — simple price-relative returns', () => {
    const rets = Stats.returns([100, 110, 99])
    expect(rets[0]).toBeCloseTo(0.1, 10)    // +10%
    expect(rets[1]).toBeCloseTo(-0.1, 10)   // -10%
  })

  it('equalWeights — sums to 1, all equal', () => {
    const w = Stats.equalWeights(4)
    expect(sumClose(w, 1)).toBe(true)
    w.forEach(x => expect(x).toBeCloseTo(0.25, 10))
  })

  it('marketWeights — proportional to cap, sums to 1', () => {
    const caps = { AAPL: 3000, MSFT: 1000 }
    const w = Stats.marketWeights(caps, ['AAPL', 'MSFT'])
    expect(w[0]).toBeCloseTo(0.75, 10)
    expect(w[1]).toBeCloseTo(0.25, 10)
    expect(sumClose(w, 1)).toBe(true)
  })

  it('marketWeights — fallback to equal when caps missing', () => {
    const w = Stats.marketWeights({}, ['A', 'B'])
    expect(w[0]).toBeCloseTo(0.5, 10)
    expect(w[1]).toBeCloseTo(0.5, 10)
  })

  it('momentum — 12m minus 1m (11m skip-last-month)', () => {
    // Build 14 months of prices: all equal → momentum = 0
    const flat = Array.from({ length: 14 }, () => 100)
    const result = Stats.momentum({ A: flat }, ['A'])
    expect(result[0]).toBeCloseTo(0, 10)
  })

  it('momentum — rising series: 12m return > 1m return → positive momentum', () => {
    // Prices go 100, 101, 102 … steadily up. 12m >> 1m → momentum > 0
    const prices = Array.from({ length: 14 }, (_, i) => 100 + i * 5)
    const result = Stats.momentum({ TREND: prices }, ['TREND'])
    expect(result[0]).toBeGreaterThan(0)
  })

  it('momentum — returns 0 when fewer than 13 prices', () => {
    const prices = [100, 110, 120]
    const result = Stats.momentum({ X: prices }, ['X'])
    expect(result[0]).toBe(0)
  })

  it('annualVol — flat series → vol = 0', () => {
    // Build returns matrix from flat prices: returns = all zeros
    const prices = { A: [100, 100, 100, 100, 100] }
    const R = Stats.returnsMatrix(prices, ['A'])
    expect(Stats.annualVol(R, 0)).toBeCloseTo(0, 8)
  })

  it('annualVol — alternating ±0.1 series: vol = 0.1×12/√11 (sample std × √12)', () => {
    // 12 monthly returns alternating ±0.1, mean=0
    // sample variance = Σx²/(n-1) = (12×0.01)/11 = 0.12/11
    // annualVol = sqrt(sampleVar × 12) = sqrt(0.12/11 × 12) = 0.1 × 12/sqrt(11)
    const monthlyReturns = [0.1, -0.1, 0.1, -0.1, 0.1, -0.1, 0.1, -0.1, 0.1, -0.1, 0.1, -0.1]
    const R = monthlyReturns.map(r => [r])
    const vol = Stats.annualVol(R, 0)
    const expected = 0.1 * 12 / Math.sqrt(11)   // = 0.3618...
    expect(vol).toBeCloseTo(expected, 6)
  })

  it('covariance — 2-asset uncorrelated series, diagonal entries > 0', () => {
    // 12 periods, two independent columns
    const R = Array.from({ length: 12 }, (_, i) => [
      Math.sin(i) * 0.05,
      Math.cos(i) * 0.03,
    ])
    const cov = Stats.covariance(R)
    expect(cov).toHaveLength(2)
    expect(cov[0][0]).toBeGreaterThan(0)
    expect(cov[1][1]).toBeGreaterThan(0)
  })
})

// ────────────────────────────────────────────
// BL engine
// ────────────────────────────────────────────
describe('BL', () => {
  // Minimal 2-asset setup
  const sigma2 = [[0.04, 0.01], [0.01, 0.09]]   // 2×2 covariance
  const wMkt = [0.6, 0.4]
  const delta = 2.5
  const tau = 0.05

  it('impliedReturns — Π = δ Σ w', () => {
    const pi = BL.impliedReturns(delta, sigma2, wMkt)
    // Π = δ * Σ * w = 2.5 * [[0.04,0.01],[0.01,0.09]] * [0.6,0.4]
    // col 0: 2.5*(0.04*0.6+0.01*0.4)=2.5*(0.024+0.004)=2.5*0.028=0.07
    // col 1: 2.5*(0.01*0.6+0.09*0.4)=2.5*(0.006+0.036)=2.5*0.042=0.105
    expect(pi[0]).toBeCloseTo(0.07, 6)
    expect(pi[1]).toBeCloseTo(0.105, 6)
  })

  it('compute — no views → muBL ≈ pi (prior)', () => {
    const { muBL, pi } = BL.compute({ delta, tau, sigma: sigma2, wMkt, P: null, Q: null, omega: null })
    expect(muBL[0]).toBeCloseTo(pi[0], 4)
    expect(muBL[1]).toBeCloseTo(pi[1], 4)
  })

  it('compute — absolute view on asset 0 pulls muBL[0] toward view Q', () => {
    const P = [[1, 0]]   // absolute view on asset 0
    const Q = [0.20]     // expect 20% return
    const omega = [0.001]
    const { muBL, pi } = BL.compute({ delta, tau, sigma: sigma2, wMkt, P, Q, omega })
    // muBL[0] should be between pi[0] (0.07) and Q[0] (0.20), closer to Q
    expect(muBL[0]).toBeGreaterThan(pi[0])
    expect(muBL[0]).toBeLessThan(Q[0])
  })

  it('constrainWeights — sums to 1', () => {
    const w = BL.constrainWeights([0.5, 0.3, 0.1, 0.1])
    expect(sumClose(w, 1)).toBe(true)
  })

  it('constrainWeights — long-only: all non-negative', () => {
    const w = BL.constrainWeights([-0.2, 0.8, 0.4, -0.1], { longOnly: true })
    w.forEach(x => expect(x).toBeGreaterThanOrEqual(0))
    expect(sumClose(w, 1)).toBe(true)
  })

  it('constrainWeights — respects maxW cap', () => {
    const w = BL.constrainWeights([0.9, 0.05, 0.05], { maxW: 0.4 })
    w.forEach(x => expect(x).toBeLessThanOrEqual(0.40 + 1e-9))
    expect(sumClose(w, 1)).toBe(true)
  })

  it('constrainWeights — infeasible maxW (< 1/n) → auto-relaxes to 1/n', () => {
    // n=4, maxW=0.1 is infeasible (4*0.1=0.4<1) → capW = max(0.1, 0.25) = 0.25
    const w = BL.constrainWeights([0.9, 0.05, 0.025, 0.025], { maxW: 0.1 })
    w.forEach(x => expect(x).toBeLessThanOrEqual(0.25 + 1e-9))
    expect(sumClose(w, 1)).toBe(true)
  })

  it('constrainWeights — infeasible minW (n*minW > 1) → floor dropped to 0', () => {
    // n=3, minW=0.4 → 3*0.4=1.2>1 → infeasible → floor = 0
    const w = BL.constrainWeights([0.5, 0.3, 0.2], { minW: 0.4 })
    expect(sumClose(w, 1)).toBe(true)
  })

  it('constrainWeights — respects feasible minW', () => {
    // n=4, minW=0.1 → 4*0.1=0.4≤1 → feasible
    const w = BL.constrainWeights([0.8, 0.1, 0.05, 0.05], { minW: 0.1 })
    w.forEach(x => expect(x).toBeGreaterThanOrEqual(0.1 - 1e-9))
    expect(sumClose(w, 1)).toBe(true)
  })

  it('portfolioReturn — dot(w, mu)', () => {
    const ret = BL.portfolioReturn([0.5, 0.5], [0.10, 0.20])
    expect(ret).toBeCloseTo(0.15, 10)
  })

  it('portfolioVol — √(wᵀΣw) for diagonal Σ', () => {
    // w=[0.5,0.5], Σ=diag([0.04,0.04]) → vol=√(0.02)
    const vol = BL.portfolioVol([0.5, 0.5], [[0.04, 0], [0, 0.04]])
    expect(vol).toBeCloseTo(Math.sqrt(0.02), 8)
  })

  it('sharpe — (ret - rf) / vol', () => {
    const w = [0.5, 0.5]
    const mu = [0.10, 0.20]
    const sigma = [[0.04, 0], [0, 0.04]]
    const rf = 0.04
    // ret = 0.15, vol = √0.02 ≈ 0.1414
    const s = BL.sharpe(w, mu, sigma, rf)
    expect(s).toBeCloseTo((0.15 - 0.04) / Math.sqrt(0.02), 6)
  })

  it('sharpe — returns 0 when vol = 0 (flat portfolio)', () => {
    const w = [1, 0]
    const sigma = [[0, 0], [0, 0]]
    const mu = [0.1, 0.1]
    const s = BL.sharpe(w, mu, sigma, 0)
    expect(s).toBe(0)
  })

  it('leverage — long-only portfolio → leverage = 1', () => {
    expect(BL.leverage([0.5, 0.3, 0.2])).toBeCloseTo(1, 8)
  })

  it('leverage — portfolio with shorts > 1', () => {
    // [1.2, -0.2] → sum=1, gross=|1.2|+|-0.2|=1.4 → leverage≈1.4
    expect(BL.leverage([1.2, -0.2])).toBeCloseTo(1.4, 8)
  })
})
