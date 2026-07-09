// Data preview table on the Setup page (§7.1)
import { Stats } from '../engine'
import { useMarketStore } from '../store/marketStore'
import { fmtCap, pct } from '../utils/format'

export default function PreviewTable() {
  const market = useMarketStore((s) => s.market)

  if (!market) {
    return (
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Ticker</th>
              <th>Name</th>
              <th>Market Cap</th>
              <th>w_mkt</th>
              <th>Annual Vol</th>
              <th>Momentum</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td colSpan={7} className="muted">
                ยังไม่มีข้อมูล — เพิ่มหุ้นแล้วกด "ดึงข้อมูลตลาด"
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    )
  }

  // Annual vol is derived on the fly from the aligned prices (MarketData
  // deliberately doesn't carry the returns matrix).
  const R = Stats.returnsMatrix(market.prices, market.tickers)

  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Ticker</th>
            <th>Name</th>
            <th>Market Cap</th>
            <th>w_mkt</th>
            <th>Annual Vol</th>
            <th>Momentum</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {market.tickers.map((t, i) => {
            const mom = market.signals[t]?.momentum ?? 0
            return (
              <tr key={t}>
                <td>
                  <b>{t}</b>
                </td>
                <td className="muted" style={{ textAlign: 'left' }}>
                  {(market.meta[t]?.name || '').slice(0, 28)}
                </td>
                <td className="mono">{fmtCap(market.marketCap[t])}</td>
                <td className="mono">{pct(market.wMkt[i])}</td>
                <td className="mono">{pct(Stats.annualVol(R, i))}</td>
                <td className={`mono ${mom >= 0 ? 'pos' : 'neg'}`}>{pct(mom)}</td>
                <td className="pos">OK</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
