# BL Optimizer — Bug Fix & Improvement Plan

> ✅ **สถานะ: แก้ครบทั้ง 10 ข้อแล้ว** (2026-06-18)
> - Critical #1–4: `engine/blacklitterman.js` (`constrainWeights`, `leverage`, `DIAG_EPS=1e-4`) + `app.js` (`capQ`, `MAX_WEIGHT`/`MIN_WEIGHT`)
> - Important #5–7: Sharpe หัก `RISK_FREE=0.05`, TE warning banners, view validation ก่อนเข้า engine
> - Nice-to-have #8–10: Expected-return warning, leverage indicator, ปุ่ม "↺ Reset to Market"
> - ทดสอบแล้ว: raw `[-99.5%, 95.1%, 30%, 74.4%]` (leverage 2.99×) → constrained `[5%, 38.3%, 16.7%, 40%]` ทุกตัวอยู่ใน [5%, 40%] และรวมเป็น 1.000

จากผลลัพธ์ที่เห็น: MSFT w* = -99.50%, Expected Return = 102.16%, Tracking Error = 28.68%

---

## 🔴 Critical — ต้องแก้ก่อน

### 1. Long-only Constraint (เหตุ: MSFT w* = -99.50%)

โมเดลไม่มีการจำกัด short position ทำให้ weight ติดลบได้อิสระ

```javascript
// หลังได้ wRaw จาก BL engine
const wClamped = wRaw.map(w => Math.max(0, w))
const wSum = wClamped.reduce((a, b) => a + b, 0)
const wStar = wClamped.map(v => v / wSum)
```

---

### 2. Max/Min Weight per Stock (เหตุ: GOOGL w* = 95.11%)

ไม่มีการจำกัด concentration risk ต่อหุ้นแต่ละตัว

```javascript
const MAX_WEIGHT = 0.40  // ไม่เกิน 40% ต่อหุ้น
const MIN_WEIGHT = 0.05  // ไม่ต่ำกว่า 5% ต่อหุ้น

let w = wRaw.map(v => Math.min(MAX_WEIGHT, Math.max(MIN_WEIGHT, v)))
const wSum = w.reduce((a, b) => a + b, 0)
const wStar = w.map(v => v / wSum)
```

---

### 3. Cap Auto View Q (เหตุ: μ_BL GOOGL = 73.42%)

GOOGL momentum = +111.56% → Auto view แปลงออกมาเป็น Q สูงเกินจริง ดัน μ_BL พุ่งผิดปกติ

```javascript
// ใน auto signal generator
const q = Math.max(0.03, Math.min(0.15, signal * 0.5))
//                 ↑ floor 3%    ↑ cap 15%
```

---

### 4. Matrix Regularization (เหตุ: inverse กระโดดสุดขั้ว)

ถ้า Σ ใกล้ singular จะทำให้ inverse ระเบิด

```javascript
// ก่อน invert sigma
const epsilon = 1e-4
for (let i = 0; i < n; i++) sigma[i][i] += epsilon
```

---

## 🟡 Important — ควรแก้

### 5. Sharpe Ratio คำนวณผิด (แสดง 2.76 ซึ่งสูงผิดปกติ)

ต้องหักด้วย risk-free rate ก่อน

```javascript
const RISK_FREE = 0.05  // 5% per year (US T-bill ปัจจุบัน)

const sharpe = (portfolioReturn - RISK_FREE) / portfolioVol
```

---

### 6. Tracking Error แสดงแต่ไม่มี Warning

28.68% สูงเกินมาตรฐาน Active Fund (ปกติ 2–8%) ควรแสดง warning

```javascript
// แสดง color + warning ตาม threshold
if (trackingError > 0.10) → แสดงสีแดง + "⚠ สูงเกิน Active Fund มาตรฐาน"
if (trackingError > 0.05) → แสดงสีเหลือง + "ระวัง"
if (trackingError <= 0.05) → แสดงสีเขียว + "ปกติ"
```

---

### 7. Validate Views ก่อนคำนวณ

ถ้า P vector ทุก element = 0 หรือ Q = 0 ควร skip view นั้น ไม่ใช่ส่งเข้า BL engine

```javascript
const validViews = views.filter(v =>
  v.enabled &&
  v.p.some(x => x !== 0) &&  // มีอย่างน้อยหนึ่งตัวที่ไม่ใช่ 0
  Math.abs(v.q) > 0.001       // Q ไม่ใช่ศูนย์
)
```

---

## 🟢 Nice to Have — แก้ทีหลังได้

### 8. แสดง Warning เมื่อ Expected Return เกิน threshold

```javascript
if (portfolioReturn > 0.30) → "⚠ Expected Return สูงผิดปกติ — ตรวจสอบ Views"
```

### 9. แสดง Leverage Indicator

```javascript
const leverage = wRaw.reduce((s, w) => s + Math.abs(w), 0)
// leverage > 1.2 → แสดง warning
```

### 10. Reset to Market Portfolio Button

กดแล้ว clear views ทั้งหมด กลับไปใช้ w_mkt ล้วนๆ เพื่อ sanity check

---

## ผลที่ควรได้หลังแก้ทั้งหมด

| Metric | ก่อนแก้ | หลังแก้ (ประมาณ) |
|--------|---------|----------------|
| MSFT w* | −99.50% | 5–15% |
| GOOGL w* | 95.11% | 30–40% |
| Expected Return | 102.16% | 15–25% |
| Volatility | 36.97% | 18–28% |
| Sharpe Ratio | 2.76 | 0.8–1.5 |
| Tracking Error | 28.68% | 5–12% |

---

## ลำดับการแก้ที่แนะนำ

```
1 → Long-only constraint         (แก้ 10 นาที, impact สูงสุด)
2 → Cap auto view Q              (แก้ 10 นาที, แก้ GOOGL μ_BL)
3 → Max/Min weight constraint    (แก้ 10 นาที, แก้ concentration)
4 → Matrix regularization        (แก้ 5 นาที, ป้องกัน edge case)
5 → Sharpe ratio formula         (แก้ 5 นาที)
6 → Tracking error warning       (แก้ 15 นาที)
7 → View validation              (แก้ 10 นาที)
```
