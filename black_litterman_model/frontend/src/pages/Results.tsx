// Page 4 — metrics, warnings, weights, returns, frontier, actions (§7.4)
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import FrontierChart from '../components/FrontierChart'
import WeightChart from '../components/WeightChart'
import { useMarketStore } from '../store/marketStore'
import { useResultsStore } from '../store/resultsStore'
import type { PortLastRun } from '../types'
import { arrow, cls, pct, signed } from '../utils/format'

export default function Results() {
  const navigate = useNavigate()
  const result = useResultsStore((s) => s.result)
  const addPort = useResultsStore((s) => s.addPort)
  const params = useMarketStore((s) => s.params)
  const rfPct = params.rf
  const [saveStatus, setSaveStatus] = useState('')
  const [copyLabel, setCopyLabel] = useState('📋 Copy Summary')

  if (!result) {
    return (
      <section className="page active">
        <div className="card">
          <p className="muted">ยังไม่มีผลลัพธ์ — กลับไปหน้า Views แล้วกด "คำนวณ Black-Litterman"</p>
          <button className="btn btn-primary" onClick={() => navigate('/views')}>
            ← ไปหน้า Views
          </button>
        </div>
      </section>
    )
  }

  const { expReturn, vol, sharpe, leverage } = result.metrics

  const exportCSV = () => {
    let csv = 'Ticker,w_mkt,w_BL,delta_weight,Pi_prior,mu_BL\n'
    result.tickers.forEach((t, i) => {
      csv += `${t},${result.wMkt[i].toFixed(4)},${result.wStar[i].toFixed(4)},${(
        result.wStar[i] - result.wMkt[i]
      ).toFixed(4)},${result.pi[i].toFixed(4)},${result.muBL[i].toFixed(4)}\n`
    })
    csv += `\nExpected Return,${expReturn.toFixed(4)}\nVolatility,${vol.toFixed(4)}\nSharpe,${sharpe.toFixed(4)}\nLeverage,${leverage.toFixed(4)}\n`
    const blob = new Blob([csv], { type: 'text/csv' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = 'bl_weights.csv'
    a.click()
  }

  const copySummary = () => {
    let txt = 'BLACK-LITTERMAN OPTIMAL PORTFOLIO\n' + '='.repeat(40) + '\n'
    result.tickers.forEach((t, i) => {
      txt += `${t.padEnd(10)} ${pct(result.wMkt[i]).padStart(8)} → ${pct(result.wStar[i]).padStart(8)}  (${signed(
        result.wStar[i] - result.wMkt[i],
      )})\n`
    })
    txt +=
      '-'.repeat(40) +
      `\nExp Return: ${pct(expReturn)}  Vol: ${pct(vol)}  Sharpe: ${sharpe.toFixed(2)}\n`
    navigator.clipboard.writeText(txt).then(() => {
      setCopyLabel('✅ Copied!')
      window.setTimeout(() => setCopyLabel('📋 Copy Summary'), 1500)
    })
  }

  const saveToPort = async () => {
    const name = prompt(`บันทึกผลลัพธ์เป็น Port ใหม่\n\nหุ้น: ${result.tickers.join(' · ')}\n\nใส่ชื่อ Port:`)
    if (!name || !name.trim()) return
    try {
      const port = await api.createPort(name.trim(), [...result.tickers])
      const weights = Object.fromEntries(result.tickers.map((t, i) => [t, result.wStar[i]]))
      // Backend PortUpdate only accepts name/tickers/last_run — weights and
      // metrics must be nested inside last_run, not sent as top-level fields.
      const last_run: PortLastRun = {
        date: new Date().toISOString().slice(0, 10),
        delta: params.delta,
        tau: params.tau,
        weights,
        metrics: { ...result.metrics },
      }
      const updated = await api.updatePort(port.id, { last_run })
      addPort(updated)
      setSaveStatus(`✅ บันทึกลง Port "${name.trim()}" แล้ว`)
      window.setTimeout(() => setSaveStatus(''), 3000)
    } catch (e) {
      alert('บันทึกไม่สำเร็จ: ' + (e as Error).message)
    }
  }

  return (
    <section className="page active">
      <div className="metrics-row">
        {(
          [
            ['Expected Return', pct(expReturn), expReturn > 0.3 ? 'neg' : ''],
            ['Volatility', pct(vol), ''],
            [`Sharpe Ratio (rf ${rfPct.toFixed(2)}%)`, sharpe.toFixed(2), ''],
            ['Leverage', leverage.toFixed(2) + '×', leverage > 1.5 ? 'neg' : ''],
          ] as [string, string, string][]
        ).map(([label, value, klass]) => (
          <div key={label} className="metric">
            <div className="m-label">{label}</div>
            <div className={`m-value ${klass}`}>{value}</div>
          </div>
        ))}
      </div>

      {result.warnings.length > 0 && (
        <div>
          {result.warnings.map((w) => (
            <div key={w} className={`warn-banner${w.startsWith('⚠') ? ' crit' : ''}`}>
              {w}
            </div>
          ))}
        </div>
      )}

      <div className="grid-2">
        <div className="card">
          <h2>Weight Comparison</h2>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>หุ้น</th>
                  <th>w_mkt</th>
                  <th>w* (BL)</th>
                  <th>Δ Change</th>
                </tr>
              </thead>
              <tbody>
                {result.tickers.map((t, i) => {
                  const d = result.wStar[i] - result.wMkt[i]
                  return (
                    <tr key={t}>
                      <td>
                        <b>{t}</b>
                      </td>
                      <td className="mono">{pct(result.wMkt[i])}</td>
                      <td className="mono">{pct(result.wStar[i])}</td>
                      <td className={`mono ${cls(d)}`}>
                        {signed(d)} {arrow(d)}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          <WeightChart result={result} />
        </div>

        <div className="card">
          <h2>Returns</h2>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>หุ้น</th>
                  <th>Π (Prior)</th>
                  <th>μ_BL</th>
                  <th>Δ Change</th>
                </tr>
              </thead>
              <tbody>
                {result.tickers.map((t, i) => {
                  const d = result.muBL[i] - result.pi[i]
                  return (
                    <tr key={t}>
                      <td>
                        <b>{t}</b>
                      </td>
                      <td className="mono">{pct(result.pi[i])}</td>
                      <td className="mono">{pct(result.muBL[i])}</td>
                      <td className={`mono ${cls(d)}`}>{signed(d)}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div className="card">
        <h2>Efficient Frontier</h2>
        <FrontierChart result={result} />
      </div>

      <div className="actions-bar">
        <button className="btn" onClick={exportCSV}>
          ⬇ Export CSV
        </button>
        <button className="btn" onClick={copySummary}>
          {copyLabel}
        </button>
        <button className="btn btn-primary" onClick={saveToPort}>
          💾 บันทึกลง Port
        </button>
      </div>
      {saveStatus && (
        <p className="status ok" style={{ textAlign: 'center', marginTop: 8 }}>
          {saveStatus}
        </p>
      )}
    </section>
  )
}
