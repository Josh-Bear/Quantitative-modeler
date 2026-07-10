// Page 1 — Stock Selector, Ports, Parameters, Data Preview (§7.1)
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import ChipInput from '../components/ChipInput'
import PreviewTable from '../components/PreviewTable'
import SliderRow from '../components/SliderRow'
import { Stats } from '../engine'
import { useMarketStore } from '../store/marketStore'
import { useResultsStore } from '../store/resultsStore'
import type { MarketData } from '../types'

type StatusKind = '' | 'ok' | 'err' | 'load'

export default function Setup() {
  const navigate = useNavigate()
  const { tickers, params, setParams, setMarket, setTickers } = useMarketStore()
  const market = useMarketStore((s) => s.market)
  const ports = useResultsStore((s) => s.ports)
  const setPorts = useResultsStore((s) => s.setPorts)

  const [status, setStatus] = useState<{ msg: string; kind: StatusKind }>({ msg: '', kind: '' })
  const [fetching, setFetching] = useState(false)

  // Load ports from the backend on mount (§7.1.2)
  useEffect(() => {
    api
      .getPorts()
      .then(setPorts)
      .catch(() => setPorts([]))
  }, [setPorts])

  const saveAsPort = async () => {
    if (!tickers.length) {
      alert('เพิ่มหุ้นก่อนบันทึก')
      return
    }
    const name = prompt(`บันทึก Port ใหม่\n\nหุ้น: ${tickers.join(' · ')}\n\nใส่ชื่อ Port:`)
    if (!name || !name.trim()) return
    try {
      await api.createPort(name.trim(), [...tickers])
      setPorts(await api.getPorts())
    } catch (e) {
      alert('บันทึกไม่สำเร็จ: ' + (e as Error).message)
    }
  }

  const deletePort = async (id: string, name: string) => {
    if (!confirm(`ลบ Port "${name}"?`)) return
    try {
      await api.deletePort(id)
      setPorts(await api.getPorts())
    } catch (e) {
      alert('ลบไม่สำเร็จ: ' + (e as Error).message)
    }
  }

  // "ดึงข้อมูลตลาด" — fetch raw prices, then compute Σ / w_mkt / signals via engine
  const fetchMarket = async () => {
    if (!tickers.length) {
      setStatus({ msg: 'เพิ่มหุ้นอย่างน้อย 1 ตัวก่อน', kind: 'err' })
      return
    }
    setFetching(true)
    setStatus({ msg: 'กำลังดึงข้อมูลจาก Yahoo Finance…', kind: 'load' })
    try {
      const raw = await api.fetchMarket(tickers, `${params.period}y`)

      const aligned = Stats.alignPrices(raw.prices) as {
        dates: string[]
        prices: MarketData['prices']
      }
      const okTickers = Object.keys(aligned.prices) // only tickers with data
      setTickers(okTickers) // drop failed ones

      const R = Stats.returnsMatrix(aligned.prices, okTickers)
      const sigma: number[][] = Stats.covariance(R)
      const wMkt: number[] = Stats.marketWeights(raw.marketCap, okTickers)
      const momentum: number[] = Stats.momentum(aligned.prices, okTickers)
      const zscore: number[] = Stats.zScore(aligned.prices, okTickers)
      const rs: number[] = Stats.relativeStrength(aligned.prices, okTickers)

      const signals: MarketData['signals'] = {}
      okTickers.forEach((t, i) => {
        signals[t] = { momentum: momentum[i], meanRev: zscore[i], relStrength: rs[i] }
      })

      const market: MarketData = {
        tickers: okTickers,
        dates: aligned.dates,
        prices: aligned.prices,
        marketCap: raw.marketCap,
        meta: raw.meta || {},
        wMkt,
        sigma,
        signals,
      }
      setMarket(market)

      const errs = Object.keys(raw.errors || {})
      setStatus({
        msg: `✅ ได้ข้อมูล ${okTickers.length} ตัว` + (errs.length ? ` · ข้าม: ${errs.join(', ')}` : ''),
        kind: 'ok',
      })
    } catch (e) {
      setStatus({ msg: `❌ ${(e as Error).message}`, kind: 'err' })
    } finally {
      setFetching(false)
    }
  }

  return (
    <section className="page active">
      <div className="grid-2">
        <div className="card">
          <h2>Stock Selector</h2>
          <ChipInput />

          <div className="ports-section">
            <div className="ports-header">
              <span className="preset-label">Ports</span>
              <div className="ports-actions">
                <button className="btn btn-sm" title="บันทึก tickers ปัจจุบันเป็น port ใหม่" onClick={saveAsPort}>
                  💾 Save as Port
                </button>
              </div>
            </div>
            <div className="port-chips-row">
              {ports.length === 0 ? (
                <span className="muted" style={{ fontSize: 12, padding: '4px 2px' }}>
                  ยังไม่มี Port — กด "Save as Port" เพื่อสร้าง
                </span>
              ) : (
                ports.map((p) => (
                  <div key={p.id} className="chip-btn port-chip" title={p.tickers.join(', ')}>
                    <div className="port-chip-top" onClick={() => setTickers([...p.tickers])}>
                      <span className="port-chip-name">{p.name}</span>
                      <span className="port-chip-count">{p.tickers.length}</span>
                      <div className="port-chip-actions">
                        <button
                          className="port-chip-del icon-btn"
                          title="ลบ Port"
                          onClick={(e) => {
                            e.stopPropagation()
                            deletePort(p.id, p.name)
                          }}
                        >
                          ✕
                        </button>
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>

        <div className="card">
          <h2>Parameters</h2>
          <SliderRow
            label="δ (Delta) — Risk aversion"
            min={1}
            max={10}
            step={0.1}
            value={params.delta}
            format={(v) => v.toFixed(1)}
            onChange={(delta) => setParams({ delta })}
          />
          <SliderRow
            label="τ (Tau) — Prior uncertainty"
            min={0.01}
            max={0.2}
            step={0.01}
            value={params.tau}
            format={(v) => v.toFixed(2)}
            onChange={(tau) => setParams({ tau })}
          />
          <SliderRow
            label="History"
            min={1}
            max={5}
            step={1}
            value={params.period}
            format={(v) => `${v} ปี`}
            onChange={(period) => setParams({ period })}
          />
          <SliderRow
            label="Risk-free rate"
            hint="(10-yr Gov Bond)"
            min={0}
            max={10}
            step={0.25}
            value={params.rf}
            format={(v) => v.toFixed(2) + '%'}
            onChange={(rf) => setParams({ rf })}
          />
          <SliderRow
            label="Min Weight"
            min={0}
            max={20}
            step={1}
            value={params.minW}
            format={(v) => v + '%'}
            onChange={(minW) =>
              // keep min < max (same clamp as legacy validateMinMax)
              setParams({ minW: minW >= params.maxW ? Math.max(0, params.maxW - 5) : minW })
            }
          />
          <SliderRow
            label="Max Weight"
            min={5}
            max={100}
            step={5}
            value={params.maxW}
            format={(v) => v + '%'}
            onChange={(maxW) =>
              setParams({
                maxW,
                ...(params.minW >= maxW ? { minW: Math.max(0, maxW - 5) } : {}),
              })
            }
          />
          {tickers.length > 0 && tickers.length * (params.maxW / 100) < 1 && (
            <p className="status err" style={{ fontSize: 11, marginTop: -4 }}>
              ⚠ Max Weight {params.maxW}% × {tickers.length} หุ้น {'<'} 100% — เป็นไปไม่ได้ที่จะกระจายครบ 100%
              ระบบจะผ่อนเป็น equal-weight ({(100 / tickers.length).toFixed(1)}%/หุ้น) อัตโนมัติ ซึ่งจะทำให้ Min
              Weight ไม่มีผลด้วย — เพิ่ม Max Weight หรือเพิ่มจำนวนหุ้น
            </p>
          )}
          <button className="btn btn-primary btn-block" disabled={fetching} onClick={fetchMarket}>
            📡 ดึงข้อมูลตลาด
          </button>
          <p className={`status ${status.kind}`}>{status.msg}</p>
        </div>
      </div>

      <div className="card">
        <h2>Data Preview</h2>
        <PreviewTable />
        {market && (
          <div className="status-bar">
            <span className="sb-note">
              Monthly · {params.period} ปี · {market.dates.length} จุด
            </span>
            <button className="btn-next" onClick={() => navigate('/ml-views')}>
              ต่อไป: ML Views →
            </button>
          </div>
        )}
      </div>
    </section>
  )
}
