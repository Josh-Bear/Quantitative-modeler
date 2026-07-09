/**
 * Unit tests — Zustand stores + format utils
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { act } from '@testing-library/react'
import { useViewsStore } from '../store/viewsStore'
import { pct, signed, round, fmtCap, cls, arrow } from '../utils/format'

// ────────────────────────────────────────────
// Format utils — pure functions
// ────────────────────────────────────────────
describe('format utils', () => {
  describe('pct', () => {
    it('positive number → "xx.xx%"', () => {
      expect(pct(0.1)).toBe('10.00%')
      expect(pct(0.1234)).toBe('12.34%')
    })
    it('zero → "0.00%"', () => expect(pct(0)).toBe('0.00%'))
    it('negative → "-5.00%"', () => expect(pct(-0.05)).toBe('-5.00%'))
  })

  describe('signed', () => {
    it('positive → "+x.xx%"', () => expect(signed(0.1)).toBe('+10.00%'))
    it('negative → "-x.xx%"', () => expect(signed(-0.05)).toBe('-5.00%'))
    it('zero → "+0.00%"', () => expect(signed(0)).toBe('+0.00%'))
  })

  describe('round', () => {
    it('rounds to 4 decimal places', () => {
      expect(round(0.123456)).toBe(0.1235)
      expect(round(0.1)).toBe(0.1)
    })
  })

  describe('cls', () => {
    it('positive → "pos"', () => expect(cls(0.1)).toBe('pos'))
    it('negative → "neg"', () => expect(cls(-0.1)).toBe('neg'))
    it('zero → ""', () => expect(cls(0)).toBe(''))
  })

  describe('arrow', () => {
    it('positive → ↑', () => expect(arrow(0.01)).toBe('↑'))
    it('negative → ↓', () => expect(arrow(-0.01)).toBe('↓'))
    it('near-zero → empty', () => expect(arrow(0.00001)).toBe(''))
  })

  describe('fmtCap', () => {
    it('trillions', () => expect(fmtCap(3e12)).toBe('3.00T'))
    it('billions', () => expect(fmtCap(2.5e9)).toBe('2.5B'))
    it('millions', () => expect(fmtCap(500e6)).toBe('500M'))
    it('undefined → —', () => expect(fmtCap(undefined)).toBe('—'))
    it('zero → —', () => expect(fmtCap(0)).toBe('—'))
  })
})

// ────────────────────────────────────────────
// viewsStore
// ────────────────────────────────────────────
describe('viewsStore', () => {
  // Reset store to initial state before each test
  beforeEach(() => {
    act(() => {
      useViewsStore.setState({
        manualViews: [],
        mlViews: [],
        mlConfig: { epochs: 250, omegaMode: 'he-litterman' },
        mlStatus: 'idle',
        mlError: null,
        lastMLResult: null,
        nextId: 1,
      })
    })
  })

  const blankView = () => ({
    enabled: true,
    type: 'absolute' as const,
    picks: { AAPL: 1, MSFT: 0 },
    q: 0.08,
    omega: 0.001,
    mlGenerated: false as const,
  })

  it('initial state — empty views, nextId=1, epochs=250', () => {
    const s = useViewsStore.getState()
    expect(s.manualViews).toHaveLength(0)
    expect(s.mlViews).toHaveLength(0)
    expect(s.nextId).toBe(1)
    expect(s.mlConfig.epochs).toBe(250)
    expect(s.mlConfig.omegaMode).toBe('he-litterman')
  })

  it('addView — allocates sequential IDs', () => {
    const { addView } = useViewsStore.getState()
    act(() => addView(blankView()))
    act(() => addView(blankView()))
    const views = useViewsStore.getState().manualViews
    expect(views[0].id).toBe(1)
    expect(views[1].id).toBe(2)
    expect(useViewsStore.getState().nextId).toBe(3)
  })

  it('addView — preserves mlGenerated: false', () => {
    const { addView } = useViewsStore.getState()
    act(() => addView(blankView()))
    expect(useViewsStore.getState().manualViews[0].mlGenerated).toBe(false)
  })

  it('removeView — removes correct view', () => {
    const { addView } = useViewsStore.getState()
    act(() => addView(blankView()))
    act(() => addView(blankView()))
    const id1 = useViewsStore.getState().manualViews[0].id
    act(() => useViewsStore.getState().removeView(id1))
    const remaining = useViewsStore.getState().manualViews
    expect(remaining).toHaveLength(1)
    expect(remaining[0].id).not.toBe(id1)
  })

  it('updateView — patches manual view, keeps mlGenerated: false', () => {
    const { addView } = useViewsStore.getState()
    act(() => addView(blankView()))
    const id = useViewsStore.getState().manualViews[0].id
    act(() => useViewsStore.getState().updateView(id, { q: 0.15 }))
    const updated = useViewsStore.getState().manualViews[0]
    expect(updated.q).toBe(0.15)
    expect(updated.mlGenerated).toBe(false)     // hardcoded in updateView
  })

  it('updateView — patches ML view, keeps mlGenerated: true', () => {
    act(() =>
      useViewsStore.setState({
        mlViews: [{ id: 99, enabled: true, type: 'absolute', picks: {}, q: 0.05, omega: 0.001, mlGenerated: true, rHat: 0.02 }],
      })
    )
    act(() => useViewsStore.getState().updateView(99, { enabled: false }))
    const mlView = useViewsStore.getState().mlViews[0]
    expect(mlView.enabled).toBe(false)
    expect(mlView.mlGenerated).toBe(true)       // hardcoded in updateView
  })

  it('activeViews — only enabled views from both lists', () => {
    act(() => {
      useViewsStore.setState({
        manualViews: [
          { id: 1, enabled: true,  type: 'absolute', picks: {}, q: 0.05, omega: 0.001, mlGenerated: false },
          { id: 2, enabled: false, type: 'absolute', picks: {}, q: 0.05, omega: 0.001, mlGenerated: false },
        ],
        mlViews: [
          { id: 3, enabled: true, type: 'absolute', picks: {}, q: 0.05, omega: 0.001, mlGenerated: true, rHat: 0 },
        ],
      })
    })
    const active = useViewsStore.getState().activeViews()
    expect(active).toHaveLength(2)
    expect(active.map(v => v.id)).toEqual([1, 3])
  })

  it('activeViews — empty when all disabled', () => {
    act(() => {
      useViewsStore.setState({
        manualViews: [{ id: 1, enabled: false, type: 'absolute', picks: {}, q: 0.05, omega: 0.001, mlGenerated: false }],
      })
    })
    expect(useViewsStore.getState().activeViews()).toHaveLength(0)
  })

  it('takeIds — allocates sequential block and advances nextId', () => {
    act(() => useViewsStore.setState({ nextId: 5 }))
    const ids = useViewsStore.getState().takeIds(3)
    expect(ids).toEqual([5, 6, 7])
    expect(useViewsStore.getState().nextId).toBe(8)
  })

  it('takeIds — consecutive calls get non-overlapping IDs', () => {
    const ids1 = useViewsStore.getState().takeIds(2)
    const ids2 = useViewsStore.getState().takeIds(2)
    const all = [...ids1, ...ids2]
    expect(new Set(all).size).toBe(4)   // all unique
  })

  it('clearManualViews — removes manual, keeps ML', () => {
    act(() => {
      useViewsStore.setState({
        manualViews: [{ id: 1, enabled: true, type: 'absolute', picks: {}, q: 0.05, omega: 0.001, mlGenerated: false }],
        mlViews: [{ id: 2, enabled: true, type: 'absolute', picks: {}, q: 0.05, omega: 0.001, mlGenerated: true, rHat: 0 }],
      })
    })
    act(() => useViewsStore.getState().clearManualViews())
    expect(useViewsStore.getState().manualViews).toHaveLength(0)
    expect(useViewsStore.getState().mlViews).toHaveLength(1)
  })

  it('setMLConfig — partial update preserves other keys', () => {
    act(() => useViewsStore.getState().setMLConfig({ omegaMode: 'svr-residual' }))
    const cfg = useViewsStore.getState().mlConfig
    expect(cfg.omegaMode).toBe('svr-residual')
    expect(cfg.epochs).toBe(250)      // unchanged
  })

  it('setMLStatus loading → error → idle cycle', () => {
    act(() => useViewsStore.getState().setMLStatus('loading'))
    expect(useViewsStore.getState().mlStatus).toBe('loading')
    expect(useViewsStore.getState().mlError).toBeNull()

    act(() => useViewsStore.getState().setMLStatus('error', 'timeout'))
    expect(useViewsStore.getState().mlStatus).toBe('error')
    expect(useViewsStore.getState().mlError).toBe('timeout')

    act(() => useViewsStore.getState().setMLStatus('idle'))
    expect(useViewsStore.getState().mlStatus).toBe('idle')
    expect(useViewsStore.getState().mlError).toBeNull()
  })
})
