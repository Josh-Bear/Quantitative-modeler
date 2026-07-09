// Zustand slice: manual + ML views and ML run config/status (§6.2)
import { create } from 'zustand'
import type { MLConfig, MLResult, MLStatus, MLView, View } from '../types'

interface ViewsStore {
  manualViews: View[]
  mlViews: MLView[]
  mlConfig: MLConfig
  mlStatus: MLStatus
  mlError: string | null
  lastMLResult: MLResult | null   // raw payload — feeds the r̂ table on MLViews
  nextId: number

  // manual view actions
  addView: (v: Omit<View, 'id'>) => void
  updateView: (id: number, patch: Partial<View>) => void
  removeView: (id: number) => void
  clearManualViews: () => void

  // ML view actions
  setMLViews: (views: MLView[]) => void
  clearMLViews: () => void
  setMLConfig: (c: Partial<MLConfig>) => void
  setMLStatus: (s: MLStatus, error?: string) => void
  setLastMLResult: (r: MLResult | null) => void

  // computed: [...manualViews, ...mlViews] filtered to enabled only
  activeViews: () => (View | MLView)[]

  // allocate ids for ML views (parseMLViews needs sequential ids)
  takeIds: (count: number) => number[]
}

export const useViewsStore = create<ViewsStore>((set, get) => ({
  manualViews: [],
  mlViews: [],
  mlConfig: { epochs: 250, omegaMode: 'he-litterman' },
  mlStatus: 'idle',
  mlError: null,
  lastMLResult: null,
  nextId: 1,

  addView: (v) =>
    set((s) => ({
      manualViews: [...s.manualViews, { ...v, id: s.nextId }],
      nextId: s.nextId + 1,
    })),

  // Patches whichever list contains the id (manual or ML) so the
  // enabled-toggle works for both kinds of view.
  updateView: (id, patch) =>
    set((s) => ({
      manualViews: s.manualViews.map((v) => (v.id === id ? { ...v, ...patch, mlGenerated: false } : v)),
      mlViews: s.mlViews.map((v) => (v.id === id ? { ...v, ...patch, mlGenerated: true } : v)),
    })),

  removeView: (id) =>
    set((s) => ({
      manualViews: s.manualViews.filter((v) => v.id !== id),
      mlViews: s.mlViews.filter((v) => v.id !== id),
    })),

  clearManualViews: () => set({ manualViews: [] }),

  setMLViews: (views) => set({ mlViews: views }),
  clearMLViews: () => set({ mlViews: [] }),
  setMLConfig: (c) => set((s) => ({ mlConfig: { ...s.mlConfig, ...c } })),
  setMLStatus: (status, error) => set({ mlStatus: status, mlError: error ?? null }),
  setLastMLResult: (r) => set({ lastMLResult: r }),

  activeViews: () => {
    const s = get()
    return [...s.manualViews, ...s.mlViews].filter((v) => v.enabled)
  },

  takeIds: (count) => {
    const start = get().nextId
    set({ nextId: start + count })
    return Array.from({ length: count }, (_, i) => start + i)
  },
}))
