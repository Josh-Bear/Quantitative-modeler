// Top nav — 4 tabs, active tab from useLocation().pathname (§3)
import { useLocation, useNavigate } from 'react-router-dom'

const TABS: { path: string; label: string }[] = [
  { path: '/setup',    label: '1 · Setup'   },
  { path: '/ml-views', label: '2 · ML Views' },
  { path: '/views',    label: '3 · Views'   },
  { path: '/results',  label: '4 · Results' },
]

export default function Navbar() {
  const { pathname } = useLocation()
  const navigate = useNavigate()

  return (
    <header className="topbar">
      <div className="brand">
        <span className="logo">Σ</span>
        <div>
          <h1>Black-Litterman Optimizer</h1>
          <p className="tagline">Market priors × your views → optimal weights</p>
        </div>
      </div>
      <nav className="tabs">
        {TABS.map((t) => (
          <button
            key={t.path}
            className={`tab${pathname === t.path ? ' active' : ''}`}
            onClick={() => navigate(t.path)}
          >
            {t.label}
          </button>
        ))}
      </nav>
    </header>
  )
}
