// Single view editor card (§7.2 Manual View Builder)
import { useMarketStore } from '../store/marketStore'
import type { View, ViewType } from '../types'

// Same Thai labels → omega values as the legacy app.js (§10)
export const CONFIDENCE: Record<string, number> = {
  'สูงมาก': 0.0002,
  'สูง': 0.0005,
  'ปานกลาง': 0.0010,
  'ต่ำ': 0.0020,
  'ต่ำมาก': 0.0050,
}

export function confidenceName(omega: number): string {
  const hit = Object.entries(CONFIDENCE).find(([, v]) => Math.abs(v - omega) < 1e-9)
  return hit ? hit[0] : 'custom'
}

interface ViewCardProps {
  view: View
  index: number
  onChange: (patch: Partial<View>) => void
  onRemove: () => void
}

export default function ViewCard({ view, index, onChange, onRemove }: ViewCardProps) {
  const tickers = useMarketStore((s) => s.tickers)
  const isKnownOmega = Object.values(CONFIDENCE).some((v) => Math.abs(v - view.omega) < 1e-9)

  return (
    <div className={`view-card${view.enabled ? '' : ' disabled'}`}>
      <div className="view-card-head">
        <span className="vtitle">View #{index + 1}</span>
        <div className="vactions">
          <label className="chk">
            <input
              type="checkbox"
              checked={view.enabled}
              onChange={(e) => onChange({ enabled: e.target.checked })}
            />{' '}
            เปิด
          </label>
          <button className="icon-btn" title="ลบ" onClick={onRemove}>
            🗑
          </button>
        </div>
      </div>
      <div className="view-type">
        <label>
          <input
            type="radio"
            name={`vt-${view.id}`}
            value="absolute"
            checked={view.type === 'absolute'}
            onChange={(e) => onChange({ type: e.target.value as ViewType })}
          />{' '}
          Absolute
        </label>
        <label>
          <input
            type="radio"
            name={`vt-${view.id}`}
            value="relative"
            checked={view.type === 'relative'}
            onChange={(e) => onChange({ type: e.target.value as ViewType })}
          />{' '}
          Relative
        </label>
      </div>
      <div className="pick-grid">
        {tickers.map((t) => (
          <div key={t} className="pick-cell">
            <span>{t}</span>
            <input
              type="number"
              step={0.5}
              value={view.picks[t] ?? 0}
              onChange={(e) =>
                onChange({ picks: { ...view.picks, [t]: parseFloat(e.target.value) || 0 } })
              }
            />
          </div>
        ))}
      </div>
      <div className="view-row">
        <div className="field">
          <label>Q — Expected return (%)</label>
          <input
            type="number"
            step={0.5}
            value={(view.q * 100).toFixed(2)}
            onChange={(e) => onChange({ q: (parseFloat(e.target.value) || 0) / 100 })}
          />
        </div>
        <div className="field">
          <label>Ω — Confidence</label>
          <select
            value={isKnownOmega ? String(view.omega) : 'custom'}
            onChange={(e) => onChange({ omega: parseFloat(e.target.value) })}
          >
            {Object.entries(CONFIDENCE).map(([name, v]) => (
              <option key={name} value={String(v)}>
                {name} ({v})
              </option>
            ))}
            {!isKnownOmega && (
              <option value="custom" disabled>
                custom ({view.omega})
              </option>
            )}
          </select>
        </div>
      </div>
    </div>
  )
}
