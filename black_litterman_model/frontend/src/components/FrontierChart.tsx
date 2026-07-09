// Efficient-frontier canvas scatter (§7.4, ported from app.js renderFrontier)
import { useEffect, useRef } from 'react'
import { BL } from '../engine'
import { useMarketStore } from '../store/marketStore'
import type { BLResult } from '../types'

interface CloudPoint {
  vol: number
  ret: number
  sharpe: number
}

export default function FrontierChart({ result }: { result: BLResult }) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const sigma = useMarketStore((s) => s.market?.sigma)
  const rfPct = useMarketStore((s) => s.params.rf)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || !sigma) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const r = result
    const rf = rfPct / 100
    const W = canvas.width
    const H = canvas.height
    const pad = { l: 60, r: 20, t: 20, b: 45 }
    ctx.clearRect(0, 0, W, H)

    // Use historical sigma (same as metrics) so chart vol matches displayed numbers.
    const cloud: CloudPoint[] = BL.randomPortfolios(r.muBL, sigma, rf, 1800)
    const blPt = { vol: BL.portfolioVol(r.wStar, sigma), ret: BL.portfolioReturn(r.wStar, r.muBL) }
    const mkPt = { vol: BL.portfolioVol(r.wMkt, sigma), ret: BL.portfolioReturn(r.wMkt, r.muBL) }
    const maxSharpe = cloud.reduce((a, b) => (b.sharpe > a.sharpe ? b : a), cloud[0])

    const all = [...cloud, blPt, mkPt]
    const xs = all.map((p) => p.vol)
    const ys = all.map((p) => p.ret)
    const xMin = Math.min(...xs) * 0.95
    const xMax = Math.max(...xs) * 1.05
    const yMin = Math.min(...ys, 0) * 1.05
    const yMax = Math.max(...ys) * 1.1

    const sx = (v: number) => pad.l + ((v - xMin) / (xMax - xMin)) * (W - pad.l - pad.r)
    const sy = (v: number) => H - pad.b - ((v - yMin) / (yMax - yMin)) * (H - pad.t - pad.b)

    // axes + grid
    ctx.strokeStyle = '#2a3340'
    ctx.fillStyle = '#8b97a7'
    ctx.font = '11px sans-serif'
    ctx.lineWidth = 1
    for (let i = 0; i <= 5; i++) {
      const gy = pad.t + (i / 5) * (H - pad.t - pad.b)
      ctx.beginPath()
      ctx.moveTo(pad.l, gy)
      ctx.lineTo(W - pad.r, gy)
      ctx.stroke()
      const val = yMax - (i / 5) * (yMax - yMin)
      ctx.fillText((val * 100).toFixed(0) + '%', 8, gy + 4)
    }
    for (let i = 0; i <= 5; i++) {
      const gx = pad.l + (i / 5) * (W - pad.l - pad.r)
      const val = xMin + (i / 5) * (xMax - xMin)
      ctx.fillText((val * 100).toFixed(0) + '%', gx - 8, H - pad.b + 18)
    }
    ctx.fillText('Volatility →', W / 2 - 30, H - 8)
    ctx.save()
    ctx.translate(16, H / 2 + 30)
    ctx.rotate(-Math.PI / 2)
    ctx.fillText('Expected Return →', 0, 0)
    ctx.restore()

    // cloud
    cloud.forEach((p) => {
      ctx.fillStyle = `rgba(79,156,255,${0.1 + p.sharpe * 0.12})`
      ctx.beginPath()
      ctx.arc(sx(p.vol), sy(p.ret), 2.4, 0, 2 * Math.PI)
      ctx.fill()
    })

    const mark = (p: { vol: number; ret: number }, color: string, label: string, rad = 7) => {
      ctx.fillStyle = color
      ctx.beginPath()
      ctx.arc(sx(p.vol), sy(p.ret), rad, 0, 2 * Math.PI)
      ctx.fill()
      ctx.strokeStyle = '#0e1117'
      ctx.lineWidth = 2
      ctx.stroke()
      ctx.fillStyle = '#e6edf3'
      ctx.font = 'bold 12px sans-serif'
      ctx.fillText(label, sx(p.vol) + 10, sy(p.ret) + 4)
    }
    mark(maxSharpe, '#2ecc71', 'Max Sharpe')
    mark(mkPt, '#f5c451', 'Market')
    mark(blPt, '#4f9cff', 'BL Optimal')
  }, [result, sigma, rfPct])

  return (
    <>
      <canvas ref={canvasRef} width={900} height={420} />
      <div className="legend">
        <span>
          <i className="dot dot-cloud" /> Random portfolios
        </span>
        <span>
          <i className="dot dot-mkt" /> Market
        </span>
        <span>
          <i className="dot dot-bl" /> BL Optimal
        </span>
        <span>
          <i className="dot dot-sharpe" /> Max Sharpe
        </span>
      </div>
    </>
  )
}
