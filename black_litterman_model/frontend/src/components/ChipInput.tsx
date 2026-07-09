// Ticker autocomplete + chips (§7.1 Stock Selector).
// Autocomplete calls api.search(q) (debounced); picks add to marketStore.tickers.
import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import { useMarketStore } from '../store/marketStore'
import type { SearchResult } from '../types'

export default function ChipInput() {
  const tickers = useMarketStore((s) => s.tickers)
  const addTicker = useMarketStore((s) => s.addTicker)
  const removeTicker = useMarketStore((s) => s.removeTicker)
  const meta = useMarketStore((s) => s.market?.meta)

  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SearchResult[]>([])
  const [open, setOpen] = useState(false)
  const [hi, setHi] = useState(-1) // keyboard-highlight index
  const [names, setNames] = useState<Record<string, string>>({})
  const timer = useRef<number | null>(null)

  useEffect(() => {
    if (timer.current) window.clearTimeout(timer.current)
    const q = query.trim()
    if (!q) {
      setOpen(false)
      setResults([])
      return
    }
    timer.current = window.setTimeout(async () => {
      try {
        setResults(await api.search(q))
      } catch {
        setResults([]) // backend offline — custom-ticker row still shown
      }
      setOpen(true)
      setHi(-1)
    }, 250)
    return () => {
      if (timer.current) window.clearTimeout(timer.current)
    }
  }, [query])

  const pick = (symbol: string, name?: string) => {
    if (name) setNames((n) => ({ ...n, [symbol.toUpperCase()]: name }))
    addTicker(symbol)
    setQuery('')
    setOpen(false)
    setHi(-1)
  }

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setHi((i) => Math.min(i + 1, results.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setHi((i) => Math.max(i - 1, -1))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      if (hi >= 0 && results[hi]) pick(results[hi].symbol, results[hi].name)
      else if (query.trim()) pick(query.trim().toUpperCase())
    } else if (e.key === 'Escape') {
      setOpen(false)
    }
  }

  const displayName = (t: string) => names[t] || meta?.[t]?.name || ''

  return (
    <>
      <div className="autocomplete-wrap">
        <div className="ticker-input-row">
          <input
            type="text"
            placeholder="พิมพ์ ticker เช่น AAPL แล้ว Enter"
            autoComplete="off"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onKeyDown}
            onBlur={() => window.setTimeout(() => setOpen(false), 120)}
          />
          <button className="btn" onClick={() => query.trim() && pick(query.trim().toUpperCase())}>
            + เพิ่ม
          </button>
        </div>
        {open && (
          <ul className="suggest-list">
            {results.length === 0 ? (
              <li
                className="suggest-item suggest-custom"
                onMouseDown={(e) => {
                  e.preventDefault()
                  pick(query.trim().toUpperCase())
                }}
              >
                <b>{query.trim().toUpperCase()}</b>
                <span>➕ เพิ่ม custom ticker</span>
              </li>
            ) : (
              results.map((r, i) => {
                const detail = [r.exchange, r.type].filter(Boolean).join(' · ')
                return (
                  <li
                    key={r.symbol}
                    className={`suggest-item${i === hi ? ' active' : ''}`}
                    onMouseDown={(e) => {
                      e.preventDefault()
                      pick(r.symbol, r.name)
                    }}
                  >
                    <b>{r.symbol}</b>
                    <span>
                      {r.name}
                      {detail ? <em> {detail}</em> : null}
                    </span>
                  </li>
                )
              })
            )}
          </ul>
        )}
      </div>
      <div className="chips">
        {tickers.map((t) => (
          <span key={t} className="chip">
            <b>{t}</b>
            {displayName(t) ? <span className="chip-name">{displayName(t)}</span> : null}{' '}
            <button title="ลบ" onClick={() => removeTicker(t)}>
              ×
            </button>
          </span>
        ))}
      </div>
    </>
  )
}
