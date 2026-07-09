/**
 * Integration tests — component render + UI flow
 * Focuses on: Navbar tab order, page structure, key UI elements
 */
import { describe, it, expect, beforeAll, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { BL, Matrix, Stats } from './loadEngine'

// ── Engine globals (required by engine/index.ts at module load) ──────────────
beforeAll(() => {
  Object.assign(window, { BL, Matrix, Stats })
})

// ── API mock (prevents real fetch in Setup useEffect) ────────────────────────
vi.mock('../api/client', () => ({
  api: {
    getPorts:   () => Promise.resolve([]),
    createPort: () => Promise.resolve({}),
    deletePort: () => Promise.resolve({}),
    updatePort: () => Promise.resolve({}),
    fetchData:  () => Promise.reject(new Error('mocked')),
    mlViews:    () => Promise.reject(new Error('mocked')),
  },
}))

// ── Render helper ─────────────────────────────────────────────────────────────
function renderAt(path: string, Component: React.ComponentType) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Component />
    </MemoryRouter>
  )
}

// ── Navbar ────────────────────────────────────────────────────────────────────
import Navbar from '../components/Navbar'

describe('Navbar', () => {
  it('renders 4 tabs', () => {
    renderAt('/setup', Navbar)
    const tabs = screen.getAllByRole('button')
    expect(tabs).toHaveLength(4)
  })

  it('tab order: Setup → ML Views → Views → Results', () => {
    renderAt('/setup', Navbar)
    const tabs = screen.getAllByRole('button').map(b => b.textContent ?? '')
    expect(tabs[0]).toMatch(/Setup/)
    expect(tabs[1]).toMatch(/ML Views/)
    expect(tabs[2]).toMatch(/Views/)
    expect(tabs[3]).toMatch(/Results/)
  })

  it('active class on current tab (setup route)', () => {
    renderAt('/setup', Navbar)
    const tabs = screen.getAllByRole('button')
    expect(tabs[0].className).toContain('active')
    expect(tabs[1].className).not.toContain('active')
  })

  it('active class on ML Views tab at /ml-views', () => {
    renderAt('/ml-views', Navbar)
    const tabs = screen.getAllByRole('button')
    expect(tabs[1].className).toContain('active')
    expect(tabs[0].className).not.toContain('active')
  })

  it('active class on Views tab at /views', () => {
    renderAt('/views', Navbar)
    const tabs = screen.getAllByRole('button')
    expect(tabs[2].className).toContain('active')
  })
})

// ── Setup page ────────────────────────────────────────────────────────────────
import Setup from '../pages/Setup'
import { act } from '@testing-library/react'
import { useMarketStore } from '../store/marketStore'

describe('Setup page', () => {
  it('renders without crashing', () => {
    renderAt('/setup', Setup)
    // should have at least the "ดึงข้อมูล" button
    expect(screen.getByRole('button', { name: /ดึงข้อมูล/i })).toBeInTheDocument()
  })

  it('"ต่อไป: ML Views" button NOT shown before data is fetched', () => {
    // Reset market store to null
    act(() => useMarketStore.setState({ market: null }))
    renderAt('/setup', Setup)
    expect(screen.queryByText(/ต่อไป.*ML Views/)).toBeNull()
  })
})

// ── ML Views page ─────────────────────────────────────────────────────────────
import MLViews from '../pages/MLViews'

describe('MLViews page', () => {
  it('renders without crashing', () => {
    renderAt('/ml-views', MLViews)
  })

  it('contains ML config card with Ω mode selector', () => {
    renderAt('/ml-views', MLViews)
    const select = screen.getByRole('combobox')   // <select> renders as combobox
    expect(select).toBeInTheDocument()
  })

  it('does NOT contain an Epochs slider', () => {
    renderAt('/ml-views', MLViews)
    // The label "Epochs" should not appear
    expect(screen.queryByText(/Epochs/i)).toBeNull()
  })

  it('contains Generate ML views button', () => {
    renderAt('/ml-views', MLViews)
    expect(screen.getByRole('button', { name: /Generate ML/i })).toBeInTheDocument()
  })

  it('Generate button is disabled before market data is loaded', () => {
    act(() => useMarketStore.setState({ market: null }))
    renderAt('/ml-views', MLViews)
    expect(screen.getByRole('button', { name: /Generate ML/i })).toBeDisabled()
  })
})

// ── Manual Views page ─────────────────────────────────────────────────────────
import ManualViews from '../pages/ManualViews'

describe('ManualViews page', () => {
  it('renders without crashing', () => {
    renderAt('/views', ManualViews)
  })

  it('does NOT contain "View Summary" heading', () => {
    renderAt('/views', ManualViews)
    expect(screen.queryByText(/View Summary/i)).toBeNull()
  })

  it('contains Auto signal checkbox: Mom', () => {
    renderAt('/views', ManualViews)
    expect(screen.getByText(/Mom/i)).toBeInTheDocument()
  })

  it('contains "⚡ Auto" button', () => {
    renderAt('/views', ManualViews)
    expect(screen.getByRole('button', { name: /Auto/i })).toBeInTheDocument()
  })

  it('contains "+ Manual" button', () => {
    renderAt('/views', ManualViews)
    expect(screen.getByRole('button', { name: /Manual/i })).toBeInTheDocument()
  })

  it('contains "คำนวณ Black-Litterman" button', () => {
    renderAt('/views', ManualViews)
    expect(screen.getByRole('button', { name: /คำนวณ/i })).toBeInTheDocument()
  })
})

// ── SliderRow ─────────────────────────────────────────────────────────────────
import SliderRow from '../components/SliderRow'

describe('SliderRow', () => {
  it('renders label and formatted value', () => {
    render(
      <SliderRow
        label="Delta"
        min={1}
        max={5}
        step={0.1}
        value={2.5}
        format={(v) => v.toFixed(1)}
        onChange={() => {}}
      />
    )
    expect(screen.getByText('Delta')).toBeInTheDocument()
    expect(screen.getByText('2.5')).toBeInTheDocument()
  })

  it('renders hint when provided', () => {
    render(
      <SliderRow
        label="Risk"
        hint="(annualised)"
        min={0}
        max={1}
        step={0.01}
        value={0.1}
        onChange={() => {}}
      />
    )
    expect(screen.getByText('(annualised)')).toBeInTheDocument()
  })

  it('uses slider-row-compact class (compact redesign)', () => {
    const { container } = render(
      <SliderRow label="X" min={0} max={1} step={0.1} value={0.5} onChange={() => {}} />
    )
    expect(container.querySelector('.slider-row-compact')).not.toBeNull()
  })
})
