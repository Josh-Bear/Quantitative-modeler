// Compact single-row slider: label [flex:1] | value [48px right-align] | range [90px]
// (FRONTEND_REDESIGN_V2.md §2)
interface SliderRowProps {
  label: string
  hint?: string
  min: number
  max: number
  step: number
  value: number
  format?: (v: number) => string
  onChange: (v: number) => void
}

export default function SliderRow({ label, hint, min, max, step, value, format, onChange }: SliderRowProps) {
  return (
    <div className="slider-row-compact">
      <div className="sr-top">
        <span className="sr-label">
          {label}
          {hint ? <span style={{ fontSize: 11, color: 'var(--muted)', marginLeft: 4 }}>{hint}</span> : null}
        </span>
        <span className="sr-val">{format ? format(value) : String(value)}</span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(+e.target.value)}
      />
    </div>
  )
}
