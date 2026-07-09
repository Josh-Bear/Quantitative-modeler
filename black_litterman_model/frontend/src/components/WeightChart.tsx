// Horizontal bar chart comparing w_mkt vs w* (§7.4, ported from app.js)
import type { BLResult } from '../types'

export default function WeightChart({ result }: { result: BLResult }) {
  const maxW = Math.max(...result.wMkt, ...result.wStar, 0.01)

  return (
    <div className="chart">
      {result.tickers.map((t, i) => (
        <div key={t} className="bar-row">
          <span>{t}</span>
          <div className="bar-track">
            <div
              className="bar-seg bar-mkt"
              style={{ width: `${((result.wMkt[i] / maxW) * 100).toFixed(1)}%` }}
            />
            <div
              className="bar-seg bar-bl"
              style={{
                width: `${((Math.max(result.wStar[i], 0) / maxW) * 100).toFixed(1)}%`,
                opacity: 0.85,
              }}
            />
          </div>
        </div>
      ))}
      <div className="bar-legend">
        <span>
          <i className="dot dot-mkt" />
          w_mkt
        </span>
        <span>
          <i className="dot dot-bl" />
          w* (BL)
        </span>
      </div>
    </div>
  )
}
