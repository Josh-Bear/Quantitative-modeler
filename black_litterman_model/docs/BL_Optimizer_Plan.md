# Black-Litterman Portfolio Optimizer — Project Plan

## Overview

Web app สำหรับ portfolio manager ที่ต้องการใช้ BL model จริงๆ — ดึงข้อมูลตลาดจริง ใส่ views ได้ทั้ง manual และ auto signal แล้วได้ optimal weights ออกมา

---

## Tech Stack

| Layer | เทคโนโลยี | เหตุผล |
|-------|----------|--------|
| Frontend | React + Vite | Fast, component-based |
| Styling | Tailwind CSS | Utility-first, responsive ง่าย |
| Charts | Recharts | React-native, ไม่ต้อง dependency หนัก |
| Data | Yahoo Finance API (yfinance) | Free, ไม่ต้อง API key |
| Math | mathjs หรือ custom numpy-style | Matrix operations สำหรับ BL |
| State | Zustand | Simple global state |
| Backend (optional) | FastAPI + Python | ถ้าอยากย้าย BL calculation ออกจาก browser |

---

## โครงสร้างหน้าเว็บ — 3 Pages

```
/setup      → เลือกหุ้น + ตั้งค่า parameters
/views      → กำหนด views (manual + auto)
/results    → ดูผลลัพธ์ weights + returns
```

---

## Page 1: Setup

### 1.1 Stock Selector

```
[ AAPL ] [ MSFT ] [ GOOGL ] [ + เพิ่ม ]

Preset: Tech | Finance | Energy | Mixed
```

- พิมพ์ ticker แล้ว enter เพิ่มได้
- ลบออกได้ทีละตัว
- validate ว่า ticker มีอยู่จริงก่อน fetch

### 1.2 Data Fetcher

- ดึง monthly price ย้อนหลัง 3 ปี จาก Yahoo Finance
- คำนวณ monthly return อัตโนมัติ
- คำนวณ Σ (Covariance Matrix) จาก returns
- ดึง Market Cap เพื่อคำนวณ w_mkt

### 1.3 Parameter Controls

```
δ (Delta)  [slider 1–10]    default: 3.0
τ (Tau)    [slider 0.01–0.2] default: 0.05
```

### 1.4 Data Preview

แสดงตาราง: `Ticker | Market Cap | Monthly Vol | Momentum Signal | Status`

---

## Page 2: Views

### 2.1 Auto Signal Generator

กดปุ่มเดียวได้ views จาก 3 signals:

| Signal | วิธีคำนวณ | แปลงเป็น |
|--------|----------|---------|
| Momentum | 12m return − 1m return | Absolute / Relative view |
| Mean Reversion | z-score ห่างจาก 52w mean | Relative view |
| Relative Strength | เทียบ performance ภายในกลุ่ม | Relative view |

แต่ละ signal → แปลงเป็น P, Q, Ω อัตโนมัติ

### 2.2 Manual View Builder

```
[ + เพิ่ม View ]

View #1  [toggle เปิด/ปิด]  [ลบ]
ประเภท:  ○ Absolute  ● Relative

P Vector:
  AAPL [+1]  MSFT [ 0]  GOOGL [-1]  NVDA [ 0]

Q (Expected return): [0.05] = 5%

Ω (Confidence):
  ○ สูงมาก (0.0002)
  ● สูง    (0.0005)
  ○ ปานกลาง (0.001)
  ○ ต่ำ    (0.002)
  ○ ต่ำมาก  (0.005)
  หรือกำหนดเอง: [______]
```

### 2.3 View Summary Panel

แสดง views ทั้งหมดในตาราง พร้อม preview ว่า view นี้ "ดัน" หุ้นไหนขึ้น/ลง

---

## Page 3: Results

### 3.1 Weight Comparison

```
         w_mkt    w* (BL)   Δ Change
AAPL     25.0%    31.2%     +6.2% ↑
MSFT     20.0%    18.5%     -1.5% ↓
GOOGL    18.0%    15.3%     -2.7% ↓
NVDA     12.0%    22.1%    +10.1% ↑↑
```

พร้อม bar chart เปรียบเทียบ

### 3.2 Returns Table

```
         Π (Prior)   μ_BL    Δ Change
AAPL       8.2%     10.5%    +2.3%
MSFT       7.8%      7.6%    -0.2%
GOOGL      9.1%      8.4%    -0.7%
NVDA       6.5%     12.3%    +5.8%
```

### 3.3 Efficient Frontier Chart

- วาด frontier curve จาก random portfolios
- จุด Market Portfolio (w_mkt)
- จุด BL Optimal (w\*)
- จุด Max Sharpe Ratio

### 3.4 Risk Metrics

```
Portfolio Expected Return:   9.8%
Portfolio Volatility:       14.2%
Sharpe Ratio:                0.69
Tracking Error vs Market:    4.1%
```

### 3.5 Export

- ดาวน์โหลด CSV ของ weights
- Copy สรุปเป็น text

---

## Data Flow

```
Yahoo Finance API
      │
      ▼
Monthly Prices (3yr)
      │
      ├── computeReturns()   → returns matrix
      ├── computeCov()       → Σ (N×N)
      ├── fetchMarketCap()   → w_mkt
      └── computeSignals()   → momentum, RSI, z-score
                │
                ▼
         BL Engine (JavaScript)
                │
         ┌──────┴──────┐
         │             │
       STEP 1        STEP 2
    Π = δΣw_mkt    P, Q, Ω
         │             │
         └──────┬───────┘
                ▼
         STEP 3: Bayesian Update
         μ_BL = M[(τΣ)⁻¹Π + PᵀΩ⁻¹Q]
                │
                ▼
         STEP 4: Optimize
         w* = (δΣ_BL)⁻¹μ_BL
                │
                ▼
            Results UI
```

---

## File Structure

```
bl-optimizer/
├── src/
│   ├── pages/
│   │   ├── Setup.jsx
│   │   ├── Views.jsx
│   │   └── Results.jsx
│   ├── components/
│   │   ├── StockSelector.jsx
│   │   ├── ViewBuilder.jsx
│   │   ├── WeightChart.jsx
│   │   ├── ReturnTable.jsx
│   │   └── EfficientFrontier.jsx
│   ├── engine/
│   │   ├── matrix.js          ← inverse, multiply, transpose
│   │   ├── stats.js           ← returns, covariance, signals
│   │   └── blacklitterman.js  ← BL core computation
│   ├── api/
│   │   └── yahoo.js           ← fetch prices + market cap
│   └── store/
│       └── useStore.js        ← Zustand global state
```

---

## ลำดับการสร้าง (Priority)

> **สถานะ:** สร้างเสร็จแล้วเป็น vanilla-JS + Python stdlib proxy (แทน React/Vite
> เพื่อให้ตรงกับ convention ของ repo — รันได้ทันทีด้วย `python server.py` ไม่ต้อง npm)
> ดู `README.md`

### Phase 1 — Core ทำงานได้ก่อน

- [x] BL engine (`engine/matrix.js` + `engine/blacklitterman.js`)
- [x] Yahoo Finance fetcher (`server.py` → `/api/data`)
- [x] Setup page พื้นฐาน
- [x] Manual views + Results table

### Phase 2 — UX ดีขึ้น

- [x] Auto signal generator (Momentum / Mean-Reversion / Relative Strength)
- [x] Efficient Frontier chart (canvas scatter)
- [x] Risk metrics (Sharpe, Tracking Error)
- [x] Responsive design

### Phase 3 — Nice to have

- [x] Export CSV + Copy summary
- [ ] Save / load portfolio config
- [ ] Multiple portfolio comparison
- [ ] Simple backtest

---

## ข้อควรระวัง

**CORS**
Yahoo Finance block direct browser call ต้องใช้ proxy เช่น `corsproxy.io` หรือทำ backend endpoint เอง

**Data Quality**
Yahoo Finance บางครั้ง missing data หรือ adjusted price ผิด ต้อง validate ก่อนคำนวณ

**Matrix Inversion**
ถ้า Σ เป็น singular (หุ้นสองตัว correlation สูงมาก) inverse จะ fail ต้อง add regularization:
```js
// เพิ่ม epsilon บน diagonal ก่อน invert
const epsilon = 1e-6;
for (let i = 0; i < n; i++) sigma[i][i] += epsilon;
```

**Short Positions**
w\* อาจติดลบได้ถ้าไม่ใส่ constraint ต้อง normalize หรือ add `w >= 0` constraint

---

## สูตรอ้างอิง

```
Prior:           Π = δ · Σ · w_mkt
Posterior Var:   M = [(τΣ)⁻¹ + PᵀΩ⁻¹P]⁻¹
Posterior Mean:  μ_BL = M · [(τΣ)⁻¹Π + PᵀΩ⁻¹Q]
Optimal Weight:  w* = (δ · Σ_BL)⁻¹ · μ_BL
Total Cov:       Σ_BL = Σ + M
```
