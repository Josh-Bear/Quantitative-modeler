// Zustand slice: BL result + saved ports (§6.3)
import { create } from 'zustand'
import type { BLResult, Port } from '../types'

interface ResultsStore {
  result: BLResult | null
  ports: Port[]

  setResult: (r: BLResult | null) => void
  setPorts: (p: Port[]) => void
  addPort: (p: Port) => void
  removePort: (id: string) => void
}

export const useResultsStore = create<ResultsStore>((set) => ({
  result: null,
  ports: [],

  setResult: (r) => set({ result: r }),
  setPorts: (p) => set({ ports: p }),
  addPort: (p) => set((s) => ({ ports: [...s.ports, p] })),
  removePort: (id) => set((s) => ({ ports: s.ports.filter((x) => x.id !== id) })),
}))
