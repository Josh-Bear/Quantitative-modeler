# FRONTEND_REDESIGN_V2.md
## Black-Litterman Optimizer — Frontend Redesign Spec (v2)

> **ใช้ไฟล์นี้สั่ง Claude Code ให้ implement การ redesign frontend**
> เขียนโดย: Cowork review pass · July 2026

---

## 1. Goal

1. **Reorder pages**: Setup → **ML Views** → Manual Views → Results
   (เดิม: Setup → Manual Views → ML Views → Results)
2. **De-clutter layout**: compact params, cleaner cards, proper visual hierarchy
3. **ML Views page**: ปรับ UI ตาม mockup ที่ approve แล้ว

---

## 2. สิ่งที่ห้ามแตะ (DO NOT MODIFY)

| Path | เหตุผล |
|------|--------|
| `backend/` | ไม่มีการเปลี่ยน API |
| `frontend/src/store/*.ts` | state logic ถูกต้องแล้ว |
| `frontend/src/api/client.ts` | API contracts ถูกต้องแล้ว |
| `frontend/src/types.ts` | types ถูกต้องแล้ว |
| `frontend/src/engine/index.ts` | engine globals ถูกต้องแล้ว |
| `frontend/src/App.tsx` | routes ไม่เปลี่ยน |
| `frontend/src/pages/Results.tsx` | user approve แล้ว |
| `frontend/src/components/ChipInput.tsx` | ใช้งานได้ดีแล้ว |
| `frontend/src/components/WeightChart.tsx` | ใช้งานได้ดีแล้ว |
| `frontend/src/components/FrontierChart.tsx` | ใช้งานได้ดีแล้ว |
| `frontend/src/components/PreviewTable.tsx` | ใช้งานได้ดีแล้ว |
| `frontend/src/components/ViewCard.tsx` | ใช้งานได้ดีแล้ว |

---

## 3. Implementation Order

ทำตามลำดับนี้เพื่อหลีก dependency ชน:

```
a) style.css           — เพิ่ม CSS classes ใหม่ก่อน
b) SliderRow.tsx       — minor refactor ก่อนที่ Setup จะใช้
c) Navbar.tsx          — สลับ tab order
d) Setup.tsx           — compact layout + next button
e) MLViews.tsx         — redesign ทั้งหน้า
f) ManualViews.tsx     — de-clutter
g) ตรวจ TypeScript     — npx tsc --noEmit ต้องผ่าน 0 error
```

---

## 4. §1 — `frontend/src/style.css`

**เพิ่ม** CSS classes ต่อไปนี้ต่อท้ายไฟล์ (ห้ามลบ class เดิม — Results.tsx ยังใช้อยู่)

> ⚠️ **Classes ต่อไปนี้มีอยู่แล้วในไฟล์ — ห้ามเพิ่มซ้ำ** (จะทำให้ override แบบไม่ตั้งใจ):
> `.field`, `.field label`, `.field select`, `.auto-controls`, `.chk`, `.views-list`,
> `.actions-bar`, `.btn-block`, `.btn-lg`, `.card-head`, `.muted`, `.pos`, `.neg`, `.mono`

**เพิ่มเฉพาะ classes ใหม่ต่อไปนี้:**

```css
/* ── Compact slider row ──────────────────────────────────────────── */
.slider-row-compact {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 6px;
}
.slider-row-compact .sr-label {
  flex: 1;
  font-size: 13px;
  color: var(--muted);
}
.slider-row-compact .sr-val {
  font-size: 13px;
  font-weight: 500;
  min-width: 48px;
  text-align: right;
  color: var(--accent);
}
.slider-row-compact input[type="range"] {
  width: 90px;
}

/* ── Horizontal divider ──────────────────────────────────────────── */
.sep {
  height: 1px;
  background: var(--border);
  margin: 12px 0;
}

/* ── Status / footer bar ─────────────────────────────────────────── */
.status-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px solid var(--border);
}
.status-bar .sb-note {
  font-size: 12px;
  color: var(--muted);
}

/* ── Return-per-stock bar chart ──────────────────────────────────── */
.rhat-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}
.rhat-ticker {
  font-size: 13px;
  font-weight: 600;
  width: 52px;
  color: var(--text);
}
.rhat-track {
  flex: 1;
  height: 7px;
  background: var(--bg-elev);
  border-radius: 4px;
  overflow: hidden;
}
.rhat-fill-pos {
  height: 100%;
  border-radius: 4px;
  background: var(--green);
}
.rhat-fill-neg {
  height: 100%;
  border-radius: 4px;
  background: var(--red);
}
.rhat-val {
  font-size: 13px;
  font-weight: 500;
  min-width: 54px;
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.rhat-val.pos { color: var(--green); }
.rhat-val.neg { color: var(--red); }

/* ── ML badge on view rows ───────────────────────────────────────── */
.badge-ml {
  display: inline-block;
  font-size: 10px;
  padding: 1px 5px;
  background: rgba(100, 72, 220, 0.18);
  color: #a78bfa;
  border-radius: 4px;
  margin-left: 4px;
  vertical-align: middle;
}

/* ── Next-page button (appears in status-bar) ────────────────────── */
.btn-next {
  padding: 6px 14px;
  font-size: 13px;
  border-radius: 6px;
  background: #4f9cff;
  color: #fff;
  border: none;
  cursor: pointer;
  font-weight: 500;
}
.btn-next:hover { background: var(--accent-dk); }
.btn-next:disabled { opacity: .4; cursor: not-allowed; }
```

---

## 5. §2 — `frontend/src/components/SliderRow.tsx`

**เปลี่ยน** จาก layout ปัจจุบัน (label+output อยู่บน, range อยู่ล่าง) เป็น **single-row compact** layout:

```tsx
// label [flex:1]   |  value [48px right-align]  |  range [90px]
interface SliderRowProps {
  label: string
  hint?: string
  min: number
  max: number
  step: number
  value: number
  format?: (v: number) => string
  onChange: (v: number) => void
}

export default function SliderRow({ label, hint, min, max, step, value, format, onChange }: SliderRowProps) {
  return (
    <div className="slider-row-compact">
      <span className="sr-label">
        {label}
        {hint ? <span style={{ fontSize: 11, color: 'var(--muted)', marginLeft: 4 }}>{hint}</span> : null}
      </span>
      <span className="sr-val">{format ? format(value) : String(value)}</span>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(+e.target.value)}
      />
    </div>
  )
}
```

> **หมายเหตุ**: ใช้ class `slider-row-compact` แทน `slider-row` — ห้ามลบ `slider-row` เดิมออกจาก CSS เพราะ Results.tsx อาจมีอ้างอิง

---

## 6. §3 — `frontend/src/components/Navbar.tsx`

เปลี่ยน **ลำดับ** tabs เท่านั้น (path ไม่เปลี่ยน — routing ยังใช้ App.tsx เดิม):

```tsx
const TABS: { path: string; label: string }[] = [
  { path: '/setup',    label: '1 · Setup'   },
  { path: '/ml-views', label: '2 · ML Views' },   // ← ขึ้นมาจากลำดับ 3
  { path: '/views',    label: '3 · Views'   },    // ← ลงไปจากลำดับ 2
  { path: '/results',  label: '4 · Results' },
]
```

ส่วน JSX ของ Navbar ไม่เปลี่ยน — แค่สลับลำดับใน TABS array

---

## 7. §4 — `frontend/src/pages/Setup.tsx`

### 7.1 เพิ่ม import

```tsx
import { useNavigate } from 'react-router-dom'
```

### 7.2 เพิ่ม hook ใน component

```tsx
const navigate = useNavigate()
```

### 7.3 Parameters card — ใช้ SliderRow (compact) เหมือนเดิม

SliderRow ถูก refactor แล้วใน §2 — ไม่ต้องเปลี่ยนอะไรใน Setup.tsx สำหรับ Parameters card

### 7.4 เพิ่ม "ต่อไป" button ใน Data Preview card

**เงื่อนไข**: button นี้แสดงก็ต่อเมื่อ `market !== null` (หลัง fetch สำเร็จ)

ต่อจาก `<PreviewTable />` ให้เพิ่ม:

```tsx
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
```

> `market` มาจาก `useMarketStore((s) => s.market)` ซึ่งมีอยู่แล้วใน Setup.tsx

---

## 8. §5 — `frontend/src/pages/MLViews.tsx`

นี่คือหน้าที่เปลี่ยนมากที่สุด ทำตามลำดับ:

### 8.1 เพิ่ม imports

```tsx
import { useEffect } from 'react'          // มีอยู่แล้ว (เพิ่มไปในรอบก่อน)
import { useNavigate } from 'react-router-dom'  // เพิ่มใหม่
```

### 8.2 เพิ่ม hook

```tsx
const navigate = useNavigate()
```

### 8.3 ลบ Epochs SliderRow ออกจาก JSX

ลบ:
```tsx
<SliderRow
  label="Epochs"
  min={10}
  max={500}
  step={10}
  value={mlConfig.epochs}
  format={(v) => String(v)}
  onChange={(epochs) => setMLConfig({ epochs })}
/>
```

> **สำคัญ**: `mlConfig.epochs` ยังคงอยู่ใน store (ค่า default = 250) และยังถูกส่งไปใน `generate()` เหมือนเดิม — แค่ไม่มี UI ให้แก้

### 8.4 ML Config card — เปลี่ยนเป็น vertical layout

แทนที่ content ใน card "ML Views Config" ด้วย:

```tsx
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
      {mlStatus === 'loading' && '⏳ Training LSTM+SVR...'}
      {mlStatus === 'done' && lastResult &&
        `✅ ${lastResult.n_absolute} absolute + ${lastResult.n_relative} relative`}
      {mlStatus === 'error' && `❌ ${mlError || 'ML views failed'}`}
    </p>
  )}
</div>
```

### 8.5 "r̂ per stock" → "Return per stock" — เปลี่ยนเป็น bar chart

แทนที่ r̂ table card ทั้งใบด้วย bar chart card:

```tsx
{lastResult && (
  <div className="card">
    <h2>Return per stock</h2>
    {(() => {
      // คำนวณ max absolute annualised r_hat สำหรับ scale bars
      const rows = lastResult.stock_order.map((t) => ({
        ticker: t,
        rHatAnn: (lastResult.r_hats[t] ?? 0) * ANNUALISE,   // annualised
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
```

> **หมายเหตุ**: `ANNUALISE = 252 / 63` ยังคงอยู่ที่ top of file

### 8.6 ML Views table — Ω แสดงเป็น decimal

ใน `<tbody>` ของตาราง ML views เปลี่ยน cell Ω จาก:

```tsx
<td className="mono">{v.omega.toExponential(3)}</td>
```

เป็น:

```tsx
<td className="mono">{v.omega.toFixed(6)}</td>
```

### 8.7 ML badge ใน table

ในคอลัมน์ Type ของตาราง ML views เพิ่ม badge:

```tsx
<td style={{ textAlign: 'left' }}>
  {v.type === 'absolute' ? 'Absolute' : 'Relative'}
  <span className="badge-ml">ML</span>
</td>
```

### 8.8 เพิ่ม "ต่อไป" footer

ต่อจากตาราง ML views (ใน card เดียวกัน):

```tsx
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
```

### 8.9 useEffect สำหรับ omegaMode sync (มีอยู่แล้ว — ตรวจให้แน่ใจ)

ต้องมี useEffect นี้อยู่แล้วจาก review pass ก่อน:

```tsx
useEffect(() => {
  if (!lastResult || !mlViews.length) return
  const ids = mlViews.map((v) => v.id)
  setMLViews(parseMLViews(lastResult, mlConfig.omegaMode, ids))
}, [mlConfig.omegaMode]) // eslint-disable-line react-hooks/exhaustive-deps
```

ถ้ายังไม่มี ให้เพิ่ม

---

## 9. §6 — `frontend/src/pages/ManualViews.tsx`

### 9.1 ลบ "View Summary" card ออก

ลบ card ที่มี `<h2>View Summary</h2>` และตารางด้านใน ออกทั้งใบ

> เหตุผล: รก + user approve mockup ที่ไม่มี View Summary แล้ว

### 9.2 รวม Auto Signal Generator เข้ากับ Manual View Builder

จาก 2 card แยก → รวมเป็น 1 card:

```tsx
<div className="card">
  {/* หัว: title + ปุ่มเพิ่ม + generate controls ──────────── */}
  <div className="card-head">
    <h2>Views</h2>
    <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
      <label className="chk">
        <input type="checkbox" checked={sigMom} onChange={(e) => setSigMom(e.target.checked)} /> Mom
      </label>
      <label className="chk">
        <input type="checkbox" checked={sigRev} onChange={(e) => setSigRev(e.target.checked)} /> Rev
      </label>
      <label className="chk">
        <input type="checkbox" checked={sigRS} onChange={(e) => setSigRS(e.target.checked)} /> RS
      </label>
      <button className="btn" onClick={generateAutoViews}>⚡ Auto</button>
      <button className="btn" onClick={addBlankView}>+ Manual</button>
    </div>
  </div>

  {/* View cards ──────────────────────────────────────────── */}
  <div className="views-list" style={{ marginTop: 12 }}>
    {manualViews.length === 0 ? (
      <p className="muted">กด "Auto" หรือ "+ Manual" เพื่อเพิ่ม view</p>
    ) : (
      manualViews.map((v, idx) => (
        <ViewCard
          key={v.id}
          view={v}
          index={idx}
          onChange={(patch) => updateView(v.id, patch)}
          onRemove={() => removeView(v.id)}
        />
      ))
    )}
  </div>
</div>
```

### 9.3 Actions bar — ไม่เปลี่ยน

```tsx
<div className="actions-bar">
  <button className="btn" onClick={resetToMarket}>
    ↺ Reset to market
  </button>
  <button className="btn btn-primary btn-lg" onClick={runBL}>
    🧮 คำนวณ Black-Litterman →
  </button>
</div>
```

> `runBL()` navigate ไป `/results` เมื่อคำนวณเสร็จ — ไม่ต้องเพิ่ม "ต่อไป" button แยก

---

## 10. Definition of Done

Claude Code ต้อง verify ทุกข้อก่อน mark เสร็จ:

- [ ] `npx tsc --noEmit` ผ่าน 0 error
- [ ] Navbar แสดง tab ลำดับ: Setup · ML Views · Views · Results
- [ ] Setup หน้า: "ต่อไป: ML Views →" ปรากฏหลัง fetch สำเร็จ, click แล้วไปหน้า `/ml-views`
- [ ] ML Views หน้า: ไม่มี Epochs slider
- [ ] ML Views หน้า: ML config card — Ω mode อยู่บน, เส้นคั่น, Generate button อยู่ล่าง, comment "LSTM + SVR · ~1–5 นาที" ใต้ปุ่ม
- [ ] ML Views หน้า: "Return per stock" แสดง bar chart (ไม่ใช่ตาราง)
- [ ] ML Views หน้า: ตาราง ML views — Ω column เป็น decimal เช่น `0.000240` (ไม่ใช่ `2.4e-4`)
- [ ] ML Views หน้า: "ต่อไป: Manual Views →" button navigate ไป `/views`
- [ ] Manual Views หน้า: ไม่มี "View Summary" card
- [ ] Manual Views หน้า: Auto-generate controls และ view cards อยู่ใน card เดียวกัน
- [ ] Results หน้า: ไม่มีการเปลี่ยนแปลง
- [ ] `style.css` — ยังมี class เดิมครบ (ไม่ได้ลบ)
- [ ] เปิดทุกหน้าด้วย browser ตรวจ console ไม่มี runtime error

---

## 11. ข้อควรระวัง

| เรื่อง | รายละเอียด |
|--------|-----------|
| `mlConfig.epochs` | ยังต้องส่งไปกับ API call ใน `generate()` แม้จะไม่มี slider แล้ว |
| `ANNUALISE` constant | ต้องคงอยู่ที่ top of MLViews.tsx (`252 / 63`) — ใช้ใน bar chart และ parseMLViews |
| SliderRow class | ใช้ `slider-row-compact` ใน CSS ใหม่ แต่ HTML tag ยังเป็น `<div className="slider-row-compact">` |
| `useEffect` omegaMode | ต้องมีอยู่ใน MLViews.tsx — ถ้าไม่มีให้เพิ่ม (ดู §8.9) |
| Results.tsx | ห้ามแตะ แม้ว่า CSS class บางตัวอาจมีชื่อซ้ำ |
