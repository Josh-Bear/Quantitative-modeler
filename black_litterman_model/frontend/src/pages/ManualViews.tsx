// Page 3 — merged Views card (auto signal generator + manual builder) + Run BL
// (de-cluttered per FRONTEND_REDESIGN_V2.md §6)
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import ViewCard from '../components/ViewCard'
import { BL } from '../engine'
import { useMarketStore } from '../store/marketStore'
import { useResultsStore } from '../store/resultsStore'
import { useViewsStore } from '../store/viewsStore'
import type { BLResult, View } from '../types'
import { pct, round } from '../utils/format'

// Same clamps as legacy app.js (§10)
const Q_FLOOR = 0.03
const Q_CAP = 0.15

// Clamp an auto-generated view's Q into [Q_FLOOR, Q_CAP], keeping its sign.
function capQ(x: number): number {
  const c = Math.max(Q_FLOOR, Math.min(Q_CAP, Math.abs(x)))
  return round(x < 0 ? -c : c)
}

function confFromStrength(s: number): number {
  if (s > 0.25) return 0.0005
  if (s > 0.12) return 0.0010
  return 0.0020
}

export default function ManualViews() {
  const navigate = useNavigate()
  const market = useMarketStore((s) => s.market)
  const tickers = useMarketStore((s) => s.tickers)
  const params = useMarketStore((s) => s.params)
  const {
    manualViews,
    addView,
    updateView,
    removeView,
    clearManualViews,
    clearMLViews,
    activeViews,
  } = useViewsStore()
  const setResult = useResultsStore((s) => s.setResult)

  const [sigMom, setSigMom] = useState(true)
  const [sigRev, setSigRev] = useState(true)
  const [sigRS, setSigRS] = useState(true)

  const blankView = (): Omit<View, 'id'> => {
    const picks: Record<string, number> = {}
    tickers.forEach((t) => (picks[t] = 0))
    return { enabled: true, type: 'absolute', picks, q: 0.05, omega: 0.0005, mlGenerated: false }
  }

  const addBlankView = () => {
    if (!tickers.length) {
      alert('เพิ่มหุ้นในหน้า Setup ก่อน')
      return
    }
    addView(blankView())
  }

  // ── Auto signal generator (ported from app.js gen-auto) ──────────
  const generateAutoViews = () => {
    if (!market) {
      alert('ดึงข้อมูลตลาดในหน้า Setup ก่อน')
      return
    }
    const T = market.tickers
    const generated: Omit<View, 'id'>[] = []

    // Momentum → absolute views: tilt prior return by momentum strength.
    if (sigMom) {
      const pi: number[] = BL.impliedReturns(params.delta, market.sigma, market.wMkt)
      T.forEach((t, i) => {
        const sig = market.signals[t].momentum
        if (Math.abs(sig) < 0.02) return // ignore weak signals
        const picks: Record<string, number> = {}
        T.forEach((x) => (picks[x] = 0))
        picks[t] = 1
        generated.push({
          enabled: true,
          type: 'absolute',
          picks,
          q: capQ(pi[i] + 0.5 * sig),
          omega: confFromStrength(Math.abs(sig)),
          mlGenerated: false,
        })
      })
    }

    // Relative strength → one relative view: best vs worst.
    if (sigRS && T.length >= 2) {
      const rs = T.map((t) => market.signals[t].relStrength)
      const best = rs.indexOf(Math.max(...rs))
      const worst = rs.indexOf(Math.min(...rs))
      if (best !== worst) {
        const picks: Record<string, number> = {}
        T.forEach((x) => (picks[x] = 0))
        picks[T[best]] = 1
        picks[T[worst]] = -1
        generated.push({
          enabled: true,
          type: 'relative',
          picks,
          q: capQ(rs[best] - rs[worst]),
          omega: 0.0010,
          mlGenerated: false,
        })
      }
    }

    // Mean reversion → relative view: most oversold vs most overbought.
    if (sigRev && T.length >= 2) {
      const z = T.map((t) => market.signals[t].meanRev)
      const cheap = z.indexOf(Math.min(...z)) // low z = below mean = upside
      const rich = z.indexOf(Math.max(...z))
      if (cheap !== rich && z[rich] - z[cheap] > 0.5) {
        const picks: Record<string, number> = {}
        T.forEach((x) => (picks[x] = 0))
        picks[T[cheap]] = 1
        picks[T[rich]] = -1
        generated.push({
          enabled: true,
          type: 'relative',
          picks,
          q: capQ(0.01 * (z[rich] - z[cheap])),
          omega: 0.0020,
          mlGenerated: false,
        })
      }
    }

    if (!generated.length) {
      alert('signal อ่อนเกินไป — ไม่มี view ที่สร้างได้')
      return
    }
    generated.forEach(addView)
  }

  // ── Run Black-Litterman (§7.4 logic) ──────────────────────────────
  const runBL = () => {
    if (!market) {
      alert('ดึงข้อมูลตลาดในหน้า Setup ก่อน')
      navigate('/setup')
      return
    }
    const T = market.tickers
    const { delta, tau } = params

    // Drop views with an all-zero pick vector or ~zero Q — no information.
    const active = activeViews().filter(
      (v) => Object.values(v.picks).some((x) => x !== 0) && Math.abs(v.q) > 0.001,
    )
    const skipped = activeViews().length - active.length

    let P: number[][] | null = null
    let Q: number[] | null = null
    let omega: number[] | null = null
    if (active.length) {
      P = active.map((v) => T.map((t) => v.picks[t] || 0))
      Q = active.map((v) => v.q)
      omega = active.map((v) => v.omega)
    }

    let out: { pi: number[]; muBL: number[]; sigmaBL: number[][] }
    try {
      out = BL.compute({ delta, tau, sigma: market.sigma, wMkt: market.wMkt, P, Q, omega })
    } catch (e) {
      alert('คำนวณไม่สำเร็จ: ' + (e as Error).message + '\n(อาจเป็นเพราะ covariance matrix singular)')
      return
    }

    const wRaw: number[] = BL.optimalWeights(delta, out.sigmaBL, out.muBL)
    const wStar: number[] = BL.constrainWeights(wRaw, {
      longOnly: true,
      minW: params.minW / 100,
      maxW: params.maxW / 100,
    })

    const metrics = {
      expReturn: BL.portfolioReturn(wStar, out.muBL) as number,
      vol: BL.portfolioVol(wStar, market.sigma) as number,
      sharpe: BL.sharpe(wStar, out.muBL, market.sigma, params.rf / 100) as number,
      leverage: BL.leverage(wRaw) as number,
    }

    const warnings: string[] = []
    if (metrics.leverage > 1.5)
      warnings.push(
        `⚠ Leverage ${metrics.leverage.toFixed(2)}× — ก่อน constraint โมเดลต้องการ short positions มาก (ถูก long-only ปรับแล้ว)`,
      )
    if (metrics.expReturn > 0.3)
      warnings.push(`⚠ Expected Return ${pct(metrics.expReturn)} สูงผิดปกติ — ตรวจสอบ Views`)
    if (skipped > 0) warnings.push(`ℹ ข้าม ${skipped} view ที่ไม่มีน้ำหนัก (pick = 0 หรือ Q ≈ 0)`)

    const result: BLResult = {
      tickers: T,
      wMkt: market.wMkt,
      wStar,
      wRaw,
      pi: out.pi,
      muBL: out.muBL,
      metrics,
      warnings,
    }
    setResult(result)
    navigate('/results')
  }

  const resetToMarket = () => {
    if (!market) {
      alert('ดึงข้อมูลตลาดในหน้า Setup ก่อน')
      navigate('/setup')
      return
    }
    clearManualViews()
    clearMLViews()
    // No views ⇒ w* collapses to w_mkt — engine sanity check.
    window.setTimeout(runBL, 0)
  }

  return (
    <section className="page active">
      <div className="card">
        {/* หัว: title + ปุ่มเพิ่ม + generate controls ──────────── */}
        <div className="card-head">
          <h2>Views</h2>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <label className="chk">
              <input type="checkbox" checked={sigMom} onChange={(e) => setSigMom(e.target.checked)} /> Mom
            </label>
            <label className="chk">
              <input type="checkbox" checked={sigRev} onChange={(e) => setSigRev(e.target.checked)} /> Rev
            </label>
            <label className="chk">
              <input type="checkbox" checked={sigRS} onChange={(e) => setSigRS(e.target.checked)} /> RS
            </label>
            <button className="btn" onClick={generateAutoViews}>⚡ Auto</button>
            <button className="btn" onClick={addBlankView}>+ Manual</button>
          </div>
        </div>

        {/* View cards ──────────────────────────────────────────── */}
        <div className="views-list" style={{ marginTop: 12 }}>
          {manualViews.length === 0 ? (
            <p className="muted">กด "Auto" หรือ "+ Manual" เพื่อเพิ่ม view</p>
          ) : (
            manualViews.map((v, idx) => (
              <ViewCard
                key={v.id}
                view={v}
                index={idx}
                onChange={(patch) => updateView(v.id, patch)}
                onRemove={() => removeView(v.id)}
              />
            ))
          )}
        </div>
      </div>

      <div className="actions-bar">
        <button className="btn" onClick={resetToMarket}>
          ↺ Reset to market
        </button>
        <button className="btn btn-primary btn-lg" onClick={runBL}>
          🧮 คำนวณ Black-Litterman →
        </button>
      </div>
    </section>
  )
}
