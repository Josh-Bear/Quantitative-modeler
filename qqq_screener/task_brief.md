# Task Brief: QQQ High Growth Screener
*สำหรับ Claude Code — ถามเพิ่มได้*

---

## เป้าหมาย

สร้าง Python script ที่ดึงข้อมูลจริงจาก yfinance แล้วรัน checklist กับหุ้นใน
NASDAQ 100 rank 26-100 (หรือ approximation) เพื่อหา shortlist หุ้นที่มีโอกาสโตสูง

Output: ตาราง shortlist พร้อม score และ Excel file ที่เปิดได้เลย

---

## Universe

ดึง NASDAQ 100 components อัตโนมัติจาก Wikipedia — ไม่ hardcode ticker list
แล้ว rank ตาม market cap จาก yfinance เพื่อให้ได้ rank ปัจจุบันจริงๆ

### Config (user ปรับได้บนสุดของ script)
```python
RANK_MIN = 26   # เริ่มที่ rank เท่าไหร่
RANK_MAX = 100  # ถึง rank เท่าไหร่
```

### วิธีดึง universe อัตโนมัติ
```python
import pandas as pd
import yfinance as yf

# Step 1: ดึง NASDAQ 100 components จาก Wikipedia
url = "https://en.wikipedia.org/wiki/Nasdaq-100"
tables = pd.read_html(url)

# หา table ที่มี column "Ticker" หรือ "Symbol"
for i, t in enumerate(tables):
    if any(col in str(t.columns) for col in ["Ticker", "Symbol"]):
        qqq_df = t
        break

# Step 2: ดึง market cap จาก yfinance แล้ว rank
tickers = qqq_df["Ticker"].tolist()  # ชื่อ column อาจต่างกัน ให้ handle ด้วย

market_caps = {}
for ticker in tickers:
    try:
        info = yf.Ticker(ticker).info
        market_caps[ticker] = info.get("marketCap", 0)
    except:
        market_caps[ticker] = 0

# Step 3: เรียง rank ตาม market cap (ใหญ่สุด = rank 1)
ranked_df = pd.DataFrame(
    list(market_caps.items()), columns=["Ticker", "MarketCap"]
).sort_values("MarketCap", ascending=False).reset_index(drop=True)

ranked_df["Rank"] = ranked_df.index + 1

# Step 4: filter ตาม RANK_MIN, RANK_MAX
universe = ranked_df[
    (ranked_df["Rank"] >= RANK_MIN) & (ranked_df["Rank"] <= RANK_MAX)
]["Ticker"].tolist()

print(f"Universe: {len(universe)} tickers (rank {RANK_MIN}-{RANK_MAX})")
print(universe)
```

### Error handling สำหรับ Wikipedia
- ถ้า table structure เปลี่ยน ให้ print ชื่อ column ทุก table แล้ว fallback ใช้ hardcoded list แทน
- Hardcoded fallback list ให้ใส่ไว้ใน script ด้วย (ใช้เฉพาะเมื่อ Wikipedia fetch ล้มเหลว)

---

## Checklist: High Growth (5 ข้อ)

หุ้นแต่ละตัวจะได้ score 0-5 จากการผ่าน/ไม่ผ่านแต่ละข้อ

| ข้อ | เงื่อนไข | ผ่านเมื่อ | yfinance field |
|-----|----------|-----------|----------------|
| 1 | Revenue growth สูง | YoY > 15% | `revenueGrowth` |
| 2 | Revenue กำลังเร่ง | growth ปีนี้ > ปีก่อน | คำนวณจาก financials quarterly |
| 3 | Gross margin สูงและขยาย | > 50% และเพิ่มขึ้น YoY | `grossMargins` |
| 4 | Rule of 40 | revenueGrowth% + FCF margin% > 40 | คำนวณ FCF = operatingCF + capex |
| 5 | Analyst revise ขึ้น | forward EPS > trailing EPS | `forwardEps` vs `trailingEps` |

**Scoring:**
- 5/5 → 🟢 ควรซื้อ
- 4/5 → 🟡 พิจารณาดู
- ≤3/5 → 🔴 ข้าม

---

## Output ที่ต้องการ

### 1. Console output
```
=== QQQ HIGH GROWTH SCREENER (rank 26-100) ===
Universe: 50 tickers | Date: 2026-06-16

TICKER  | Rev Growth | Accelerating | Gross Margin | Rule of 40 | Analyst Rev | SCORE | SIGNAL
--------|------------|--------------|--------------|------------|-------------|-------|-------
CRWD    |   32%  ✅  |     ✅       |   75%  ✅    |   58  ✅   |     ✅      |  5/5  |  🟢
DDOG    |   27%  ✅  |     ✅       |   80%  ✅    |   44  ✅   |     ✅      |  5/5  |  🟢
...

🟢 BUY (5/5): CRWD, DDOG, NET
🟡 WATCH (4/5): ZS, SNOW, MDB
🔴 SKIP: ทุกตัวที่เหลือ
```

### 2. Excel file: `qqq_screener_output.xlsx`
- Sheet 1: `Screener Results` — ตารางเต็มทุก ticker พร้อม raw data + score + signal
- Sheet 2: `Shortlist` — เฉพาะตัวที่ score ≥ 4 เรียงจาก score สูงสุด
- Sheet 3: `Data Quality` — ticker ที่ดึงข้อมูลไม่ได้ หรือ field missing

---

## Technical Requirements

```
Libraries: yfinance, pandas, numpy, openpyxl
Python: 3.10+
Error handling: ถ้า field ใดใดดึงไม่ได้ให้ mark เป็น N/A และ skip ข้อนั้น (ไม่ crash)
Rate limiting: ใส่ time.sleep(0.5) ระหว่าง ticker เพื่อไม่โดน block
```

---

## Edge Cases ที่ต้องจัดการ

- **FCF ติดลบ** — Rule of 40 ยังคำนวณได้ (อาจได้ค่าต่ำ) แต่ให้ flag ไว้ใน output
- **ข้อมูล missing** — ถ้า field หลักหายให้ skip ข้อนั้น ไม่ให้คะแนน ไม่ crash
- **Revenue acceleration (ข้อ 2)** — ถ้าดึง quarterly data ไม่ได้ ให้ mark N/A และ skip
- **Ticker ที่หลุด index** — ดึงข้อมูลได้แต่อาจไม่อยู่ใน QQQ แล้ว ให้แสดงผลตามปกติ

---

## ไม่ต้องทำ (out of scope)

- Backtest
- Exit rule
- Portfolio weighting
- Visualization / chart
- Real-time data / websocket

---

## เพิ่มเติมถ้าทำได้ (nice to have)

- ให้ user กำหนด threshold ได้ใน config section บนสุดของ script เช่น
  `REV_GROWTH_THRESHOLD = 0.15` แทนที่จะ hardcode
- แสดง % ที่ขาดไปจาก threshold เช่น "Rule of 40: 35 (ขาด 5)"
