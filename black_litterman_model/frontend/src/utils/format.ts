// Formatting helpers shared across pages (ported from app.js)
export function pct(x: number): string {
  return (x * 100).toFixed(2) + '%'
}

export function signed(x: number): string {
  return (x >= 0 ? '+' : '') + (x * 100).toFixed(2) + '%'
}

export function arrow(x: number): string {
  return x > 0.0001 ? '↑' : x < -0.0001 ? '↓' : ''
}

export function cls(x: number): string {
  return x > 0 ? 'pos' : x < 0 ? 'neg' : ''
}

export function round(x: number): number {
  return Math.round(x * 10000) / 10000
}

export function fmtCap(c: number | undefined): string {
  if (!c) return '—'
  if (c >= 1e12) return (c / 1e12).toFixed(2) + 'T'
  if (c >= 1e9) return (c / 1e9).toFixed(1) + 'B'
  if (c >= 1e6) return (c / 1e6).toFixed(0) + 'M'
  return String(c)
}
