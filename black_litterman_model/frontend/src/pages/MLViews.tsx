// Page 2 — dedicated ML views page: config, return bar chart, views list
// (redesigned per FRONTEND_REDESIGN_V2.md §5)
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { useMarketStore } from '../store/marketStore'
import { useViewsStore } from '../store/viewsStore'
import type { MLResult, MLView, OmegaMode } from '../types'
import { pct, round } from '../utils/format'

const ML_Q_CLAMP = 0.30 // extreme-r̂ guard (§10)
const ANNUALISE = 252 / 63 // r_hats are raw 63-day returns; Q is already annualised

const OMEGA_LABELS: Record<OmegaMode, string> = {
  'he-litterman': 'He-Litterman',
  'svr-residual': 'SVR Residual',
  blend: 'Blend (50/50)',
}

// Convert the /api/ml-views payload into MLView objects (same P/Q/omega
// extraction as legacy app.js parseMLViews, tagged mlGenerated + rHat).
// prevEnabled preserves the user's "Used" toggles across re-parses (Ω-mode
// switch + page remount); omitted on a fresh generation → all default on.
function parseMLViews(
  result: MLResult,
  omegaMode: OmegaMode,
  ids: number[],
  prevEnabled?: Record<number, boolean>,
): MLView[] {
  const stockOrder = result.stock_order
  const omegaArr = result.omega[omegaMode]

  return result.P.map((pRow, k) => {
    const picks: Record<string, number> = {}
    stockOrder.forEach((t, i) => {
      if (pRow[i] !== 0) picks[t] = pRow[i]
    })
    const type = pRow.some((x) => x < 0) ? ('relative' as const) : ('absolute' as const)
    const q = Math.max(-ML_Q_CLAMP, Math.min(ML_Q_CLAMP, result.Q[k]))
    const longTicker = stockOrder.find((_, i) => pRow[i] > 0)
    const id = ids[k]
    return {
      id,
      enabled: prevEnabled ? (prevEnabled[id] ?? true) : true,
      type,
      picks,
      q: round(q),
      omega: omegaArr[k],
      mlGenerated: true as const,
      rHat: (longTicker && result.r_hats[longTicker]) || 0,
    }
  })
}

export default function MLViews() {
  const navigate = useNavigate()
  const market = useMarketStore((s) => s.market)
  const params = useMarketStore((s) => s.params)
  const {
    mlViews,
    mlConfig,
    mlStatus,
    mlError,
    setMLConfig,
    setMLViews,
    clearMLViews,
    setMLStatus,
    updateView,
    takeIds,
  } = useViewsStore()

  const [lastResult, setLastResult] = [
    useViewsStore((s) => s.lastMLResult),
    useViewsStore((s) => s.setLastMLResult),
  ]

  // Polled while a training run is in flight so the status line can show
  // "Finished k/n" (k = stocks trained so far, n = stocks sent) instead of
  // a static spinner. Cleared as soon as the run leaves "loading".
  const [progress, setProgress] = useState<{ completed: number; total: number } | null>(null)
  const pollRef = useRef<number | null>(null)

  useEffect(() => {
    if (mlStatus !== 'loading') {
      if (pollRef.current !== null) {
        window.clearInterval(pollRef.current)
        pollRef.current = null
      }
      setProgress(null)
      return
    }
    setProgress({ completed: 0, total: 0 })
    const poll = () => {
      api.mlViewsProgress().then(setProgress).catch(() => {})
    }
    poll()
    pollRef.current = window.setInterval(poll, 1000)
    return () => {
      if (pollRef.current !== null) window.clearInterval(pollRef.current)
      pollRef.current = null
    }
  }, [mlStatus])

  // Re-parse mlViews whenever omegaMode changes so BL always uses the selected Ω.
  // Also fires on mount (page remount) — preserve each row's "Used" toggle so
  // leaving and returning to the page doesn't silently re-enable disabled views.
  useEffect(() => {
    if (!lastResult || !mlViews.length) return
    const ids = mlViews.map((v) => v.id) // reuse existing IDs to avoid React key churn
    const prevEnabled = Object.fromEntries(mlViews.map((v) => [v.id, v.enabled]))
    setMLViews(parseMLViews(lastResult, mlConfig.omegaMode, ids, prevEnabled))
  }, [mlConfig.omegaMode]) // eslint-disable-line react-hooks/exhaustive-deps

  // mlConfig.epochs (default 250) is still sent — there's just no slider UI for it.
  const generate = async () => {
    if (!market || mlStatus === 'loading') return
    setMLStatus('loading')
    try {
      const result = await api.mlViews(market.tickers, params.tau, params.delta, mlConfig.epochs)
      setLastResult(result)
      const ids = takeIds(result.P.length)
      setMLViews(parseMLViews(result, mlConfig.omegaMode, ids))
      setMLStatus('done')
    } catch (e) {
      setMLStatus('error', (e as Error).message)
    }
  }

  const mse = (x: number | undefined) => (x == null || !isFinite(x) ? '—' : x.toFixed(4))

  return (
    <section className="page active">
      <div className="card">
        <h2>ML config</h2>

        {/* บน: Ω mode selector */}
        <div className="field">
          <label>Ω mode</label>
          <select
            value={mlConfig.omegaMode}
            onChange={(e) => setMLConfig({ omegaMode: e.target.value as OmegaMode })}
          >
            {(Object.keys(OMEGA_LABELS) as OmegaMode[]).map((m) => (
              <option key={m} value={m}>
                {OMEGA_LABELS[m]}
              </option>
            ))}
          </select>
        </div>

        {/* เส้นคั่น */}
        <div className="sep" />

        {/* ล่าง: Generate button + comment */}
        <button
          className="btn btn-primary btn-block"
          disabled={!market || mlStatus === 'loading'}
          onClick={generate}
        >
          🤖 Generate ML views
        </button>
        <p style={{ fontSize: 11, color: '#8b97a7', textAlign: 'center', marginTop: 6 }}>
          LSTM + SVR · ~1–5 นาที
        </p>

        {/* Status message อยู่ใต้ comment */}
        {mlStatus !== 'idle' && (
          <p style={{ fontSize: 12, marginTop: 8, textAlign: 'center' }}>
            {mlStatus === 'loading' &&
              (progress && progress.total > 0
                ? `⏳ Finished ${progress.completed}/${progress.total}`
                : '⏳ Training LSTM+SVR...')}
            {mlStatus === 'done' && lastResult &&
              `✅ ${lastResult.n_absolute} absolute + ${lastResult.n_relative} relative`}
            {mlStatus === 'error' && `❌ ${mlError || 'ML views failed'}`}
          </p>
        )}
      </div>

      {lastResult && (
        <div className="card">
          <h2>Return per stock</h2>
          {(() => {
            // คำนวณ max absolute annualised r_hat สำหรับ scale bars
            const rows = lastResult.stock_order.map((t) => ({
              ticker: t,
              rHatAnn: (lastResult.r_hats[t] ?? 0) * ANNUALISE, // annualised
            })).sort((a, b) => b.rHatAnn - a.rHatAnn)

            const maxAbs = Math.max(...rows.map((r) => Math.abs(r.rHatAnn)), 0.01)

            return rows.map((r) => {
              const widthPct = Math.round((Math.abs(r.rHatAnn) / maxAbs) * 100)
              return (
                <div key={r.ticker} className="rhat-bar">
                  <span className="rhat-ticker">{r.ticker}</span>
                  <div className="rhat-track">
                    <div
                      className={r.rHatAnn >= 0 ? 'rhat-fill-pos' : 'rhat-fill-neg'}
                      style={{ width: `${widthPct}%` }}
                    />
                  </div>
                  <span className={`rhat-val ${r.rHatAnn >= 0 ? 'pos' : 'neg'}`}>
                    {r.rHatAnn >= 0 ? '+' : ''}{(r.rHatAnn * 100).toFixed(1)}%
                  </span>
                </div>
              )
            })
          })()}
        </div>
      )}

      {lastResult && (
        <div className="card">
          <h2>Model Diagnostics</h2>
          <p className="muted">
            จำนวนวันที่ fetch ได้ · LSTM validation MSE · SVR train/test MSE ต่อหุ้น (test = validation
            slice 20% ท้ายสุดที่โมเดลไม่เคยเห็น)
          </p>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Ticker</th>
                  <th>Sector</th>
                  <th>Days</th>
                  <th>Train / Val</th>
                  <th>LSTM val MSE</th>
                  <th>SVR train MSE</th>
                  <th>SVR test MSE</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {lastResult.diagnostics.map((d) => (
                  <tr key={d.ticker}>
                    <td>
                      <b>{d.ticker}</b>
                    </td>
                    <td style={{ textAlign: 'left' }}>{d.sector || '—'}</td>
                    <td>{d.n_rows || 0}</td>
                    <td>{d.success ? `${d.n_train} / ${d.n_val}` : '—'}</td>
                    <td className="mono">{mse(d.lstm_val_mse)}</td>
                    <td className="mono">{mse(d.svr_train_mse)}</td>
                    <td className="mono">{mse(d.svr_test_mse)}</td>
                    <td title={d.error || ''}>{d.success ? '✅' : `❌ ${d.error || 'failed'}`}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div className="card">
        <div className="card-head">
          <h2>ML Views</h2>
          <button className="btn" disabled={!mlViews.length} onClick={clearMLViews}>
            🗑 Clear all ML views
          </button>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>#</th>
                <th>ประเภท</th>
                <th>Picks</th>
                <th>r̂ (raw, 63d)</th>
                <th>Q (annualised, clamped)</th>
                <th>Ω</th>
                <th>Used</th>
              </tr>
            </thead>
            <tbody>
              {mlViews.length === 0 ? (
                <tr>
                  <td colSpan={7} className="muted">
                    ยังไม่มี ML views — กด "Generate ML views"
                  </td>
                </tr>
              ) : (
                mlViews.map((v, i) => {
                  const picks = Object.entries(v.picks).filter(([, x]) => x !== 0)
                  return (
                    <tr key={v.id}>
                      <td>{i + 1}</td>
                      <td style={{ textAlign: 'left' }}>
                        {v.type === 'absolute' ? 'Absolute' : 'Relative'}
                        <span className="badge-ml">ML</span>
                      </td>
                      <td style={{ textAlign: 'left' }}>
                        {picks.map(([t, x]) => `${t}:${x > 0 ? '+' : ''}${x}`).join('  ')}
                      </td>
                      <td className="mono">{pct(v.rHat)}</td>
                      <td className="mono">{pct(v.q)}</td>
                      <td className="mono">{v.omega.toFixed(6)}</td>
                      <td>
                        <input
                          type="checkbox"
                          checked={v.enabled}
                          onChange={(e) => updateView(v.id, { enabled: e.target.checked })}
                        />
                      </td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </div>
        <div className="status-bar">
          <span className="sb-note">
            {mlViews.length > 0
              ? `${lastResult?.n_absolute ?? 0} absolute · ${lastResult?.n_relative ?? 0} relative`
              : 'ยังไม่มี ML views'}
          </span>
          <button
            className="btn-next"
            disabled={!mlViews.length}
            onClick={() => navigate('/views')}
          >
            ต่อไป: Manual Views →
          </button>
        </div>
      </div>
    </section>
  )
}
