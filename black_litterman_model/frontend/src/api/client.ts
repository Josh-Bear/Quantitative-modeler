// All fetch() calls to the FastAPI backend (docs/FRONTEND_REDESIGN.md §5).
// Every backend response is wrapped as { ok: true, data: ... } — unwrap here.
// Each method throws on a non-ok response.

import type { MarketData, MLResult, Port, SearchResult } from '../types'

const API_BASE = 'http://localhost:8000'

interface FetchMarketRaw {
  prices: MarketData['prices']
  marketCap: MarketData['marketCap']
  meta: MarketData['meta']
  errors: Record<string, string>
}

async function unwrap<T>(res: Response): Promise<T> {
  let json: { ok?: boolean; data?: T; detail?: string; error?: string } = {}
  try {
    json = await res.json()
  } catch {
    /* non-JSON error body */
  }
  if (!res.ok || json.ok === false) {
    throw new Error(json.detail || json.error || `HTTP ${res.status}`)
  }
  return json.data as T
}

export const api = {
  // GET /api/data?tickers=A,B&period=3y
  async fetchMarket(tickers: string[], period: string): Promise<FetchMarketRaw> {
    const url = `${API_BASE}/api/data?tickers=${encodeURIComponent(tickers.join(','))}&period=${period}`
    return unwrap<FetchMarketRaw>(await fetch(url))
  },

  // GET /api/search?q=apple
  async search(q: string): Promise<SearchResult[]> {
    const res = await fetch(`${API_BASE}/api/search?q=${encodeURIComponent(q)}`)
    const data = await unwrap<{ results: SearchResult[] }>(res)
    return data.results || []
  },

  // POST /api/ml-views  body: { tickers, tau, delta, epochs }
  async mlViews(tickers: string[], tau: number, delta: number, epochs: number): Promise<MLResult> {
    const res = await fetch(`${API_BASE}/api/ml-views`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tickers, tau, delta, epochs }),
    })
    return unwrap<MLResult>(res)
  },

  // GET /api/ml-views/progress — polled while a training run is in flight
  async mlViewsProgress(): Promise<{ completed: number; total: number }> {
    return unwrap<{ completed: number; total: number }>(
      await fetch(`${API_BASE}/api/ml-views/progress`),
    )
  },

  // GET /api/ports
  async getPorts(): Promise<Port[]> {
    return unwrap<Port[]>(await fetch(`${API_BASE}/api/ports`))
  },

  // POST /api/ports  body: { name, tickers }
  async createPort(name: string, tickers: string[]): Promise<Port> {
    const res = await fetch(`${API_BASE}/api/ports`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, tickers }),
    })
    return unwrap<Port>(res)
  },

  // PUT /api/ports/:id  body: Partial<Port>
  async updatePort(id: string, data: Partial<Port>): Promise<Port> {
    const res = await fetch(`${API_BASE}/api/ports/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
    return unwrap<Port>(res)
  },

  // DELETE /api/ports/:id
  async deletePort(id: string): Promise<void> {
    const res = await fetch(`${API_BASE}/api/ports/${id}`, { method: 'DELETE' })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
  },
}
