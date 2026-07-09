// Zustand slice: tickers, parameters and fetched market data (§6.1)
import { create } from 'zustand'
import type { MarketData, Params } from '../types'

interface MarketStore {
  tickers: string[]
  params: Params
  market: MarketData | null

  addTicker: (t: string) => void
  removeTicker: (t: string) => void
  setTickers: (ts: string[]) => void
  setParams: (p: Partial<Params>) => void
  setMarket: (m: MarketData | null) => void
}

export const useMarketStore = create<MarketStore>((set) => ({
  tickers: ['AAPL', 'MSFT', 'GOOGL', 'NVDA'],
  params: { delta: 3.0, tau: 0.05, period: 10, rf: 4.5, minW: 1, maxW: 10 },
  market: null,

  addTicker: (t) =>
    set((s) => {
      const up = t.trim().toUpperCase()
      if (!up || s.tickers.includes(up)) return s
      return { tickers: [...s.tickers, up] }
    }),
  removeTicker: (t) => set((s) => ({ tickers: s.tickers.filter((x) => x !== t) })),
  setTickers: (ts) => set({ tickers: ts }),
  setParams: (p) => set((s) => ({ params: { ...s.params, ...p } })),
  setMarket: (m) => set({ market: m }),
}))
