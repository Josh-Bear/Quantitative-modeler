# ML Views Design — LSTM+SVR → P, Q, Ω Integration
## สำหรับ Claude Code ในการ implement

---

## 1. Overview

เพิ่ม "Generate ML Views" button ใน `black_litterman_model` web app โดย:
- Backend Python คำนวณ LSTM+SVR per stock → ได้ r̂ และ ω
- สร้าง P (absolute + relative by sector), Q (r̂), Ω (3 modes)
- ส่งกลับมาให้ frontend populate views เหมือน auto-generate เดิม

**ไม่แตะ BL engine เดิม (`engine/`) เลย** — แค่เพิ่ม views เข้าไป

---

## 2. สิ่งที่ต้องทำ (4 ส่วน)

### ส่วนที่ 1: `backend/ml_views.py` (ไฟล์ใหม่)

ไฟล์หลักที่ทำงานทั้งหมด แบ่งเป็น 4 functions:

#### 2.1.1 `fetch_features(tickers, period="2y")`

```python
def fetch_features(tickers: list[str], period: str = "2y") -> dict:
    """
    ดึง OHLCV daily จาก yfinance แล้วคำนวณ 8 indicators

    Input:  tickers = ["AAPL", "MSFT", ...]
    Output: {
        "AAPL": {
            "features": pd.DataFrame,  # columns = 8 indicators, index = date
            "close":    pd.Series,     # adjusted close per day
            "sector":   str,           # GICS sector จาก yf.Ticker.info
        },
        "MSFT": { ... },
        "errors": { "XYZ": "reason" }  # tickers ที่ fail
    }

    8 indicators (เหมือน bl_model_port_optimization/src/features.py):
    - rsi:          RSI(14)         ใช้ pandas_ta หรือคำนวณเอง
    - atr:          ATR(14)
    - macd_hist:    MACD histogram (line - signal)
    - keltner_pos:  (close - KC_lower) / (KC_upper - KC_lower)
    - bb_pctb:      Bollinger %B
    - squeeze_on:   1 ถ้า BB อยู่ใน KC, else 0
    - momentum_pct: ROC(10) = close/close.shift(10) - 1
    - ht_dcperiod:  Hilbert Transform Dominant Cycle Period (ต้องใช้ TA-Lib)
                    → ถ้า TA-Lib ไม่ได้ติดตั้ง ให้ใส่ค่า 0.0 แทนและ log warning

    Notes:
    - ตัด warmup rows 50 แถวแรกออก (NaN จาก indicators)
    - ใช้ daily data ไม่ใช่ monthly (ต่างจาก /api/data ที่ใช้ monthly)
    - period "2y" = 2 ปี ≈ 504 trading days → พอสำหรับ train
    - บันทึก sector จาก yf.Ticker(t).info.get("sector", "Unknown")
    """
```

#### 2.1.2 `train_lstm_svr(ticker, data, epochs=30, val_fraction=0.2, hidden=64, n_layers=4)`

```python
def train_lstm_svr(ticker: str, data: dict, epochs: int = 30,
                   val_fraction: float = 0.2,
                   hidden: int = 64, n_layers: int = 4) -> dict:
    """
    Architecture A: LSTM (feature extractor) → SVR → r̂

    Input:
        ticker: str
        data:   dict จาก fetch_features() สำหรับ ticker นี้
                { "features": DataFrame, "close": Series }
        epochs: จำนวน LSTM epochs (default 30 สำหรับ web app — เร็วพอ)
        val_fraction: 0.2 = last 20% เป็น validation (chronological เสมอ)

    Process:
        1. สร้าง 30-day rolling windows จาก features
           X shape: (n_samples, 30, 8)
           y shape: (n_samples,) = 63-day forward return
              target(t) = close[t+63] / close[t] - 1
              ใช้ overlapping windows (stride=1)

        2. Chronological 80/20 split — ห้าม shuffle
           train: แถวแรก, val: 20% ท้าย

        3. Standardize features: fit StandardScaler บน train เท่านั้น
           แล้ว transform ทั้ง train + val + prediction window

        4. Train LSTM (Architecture A — Option A):
           - nn.LSTM(input_size=8, hidden_size=hidden, num_layers=n_layers,
                     batch_first=True, dropout=0.4 ถ้า n_layers > 1)
           - Linear head: hidden → 1
           - loss: MSELoss
           - optimizer: Adam(lr=0.001)
           - early stopping: patience=10 epochs ไม่ improve val MSE
           - หลัง train เสร็จ: discard linear head, เก็บแค่ LSTM encoder

        5. Extract hidden states:
           encode(x) → h_n[-1] → (batch, hidden)
           สร้าง H_train (n_train, hidden), H_val (n_val, hidden)

        6. Train SVR(kernel='rbf', C=5, epsilon=0.01) บน H_train, y_train

        7. คำนวณ ω (residual variance):
           pred_val = svr.predict(H_val)
           omega_i  = np.var(pred_val - y_val)
           ← ต้องใช้ val set เท่านั้น ห้ามใช้ train set

        8. Predict r̂ จาก 30-day window ล่าสุด (สุดท้ายก่อน predict):
           X_pred = features[-30:] (scaled)
           H_pred = lstm.encode(X_pred)
           r_hat  = svr.predict(H_pred)[0]

    Output: {
        "ticker":  str,
        "r_hat":   float,   # predicted 63-day return
        "omega":   float,   # SVR residual variance on val set
        "sector":  str,     # จาก fetch_features
        "success": bool,
        "error":   str or None
    }

    Error handling:
    - ถ้า data น้อยกว่า 200 rows หลัง warmup → return success=False
    - ถ้า torch ไม่ได้ติดตั้ง → return success=False พร้อม error message
    - ทุก exception ให้ catch และ return success=False ไม่ crash server
    """
```

#### 2.1.3 `build_views(results, sigma, tau)`

```python
def build_views(results: list[dict], sigma: np.ndarray, tau: float = 0.05) -> dict:
    """
    สร้าง P, Q, และ Ω ทั้ง 3 modes จาก results ของ train_lstm_svr

    Input:
        results: list ของ dict จาก train_lstm_svr (เฉพาะ success=True)
                 [{"ticker","r_hat","omega","sector"}, ...]
        sigma:   np.ndarray (N×N) covariance matrix ของ N stocks
                 คำนวณจาก daily returns แล้ว annualize × 252
        tau:     float = 0.05 (BL parameter)

    ─── P และ Q (เหมือนกันทุก omega mode) ───────────────────────

    Stock ordering: เรียง alphabetically by sector แล้วตาม ticker
                   → ต้องส่ง stock_order กลับไปด้วย เพื่อให้ frontend
                     รู้ว่า index ไหนคือหุ้นอะไร

    Absolute views (1 view ต่อ 1 stock):
        P_abs[i, i] = 1  (one-hot)
        Q_abs[i]    = r_hat[i]

    Relative views (1 view ต่อ sector ที่มี ≥ 2 stocks):
        ภายใน sector: rank by r_hat descending → top vs 2nd
        P_rel[k, top_idx]  = +1
        P_rel[k, sec_idx]  = -1
        Q_rel[k]           = r_hat[top] - r_hat[second]

        ถ้า sector มี 1 stock → ข้ามไป ไม่สร้าง relative view
        ถ้า sector มี 3+ stocks → สร้างแค่ top vs 2nd เท่านั้น

    P = stack(P_abs, P_rel)    shape: (K, N)
    Q = concat(Q_abs, Q_rel)   shape: (K,)
    โดย K = N + n_sectors_with_2plus_stocks

    ─── Ω — 3 modes ────────────────────────────────────────────

    tau_sigma = tau × sigma   (N×N)

    Mode 1: "he-litterman"
        Ω_k = P[k] @ tau_sigma @ P[k].T   (scalar per view)
        → Ω = diag([Ω_0, Ω_1, ..., Ω_K])
        ความหมาย: uncertainty ∝ prior covariance structure

    Mode 2: "svr-residual"
        Absolute view k (stock i):
            Ω_k = omega_i
        Relative view k (stock i vs j):
            Ω_k = omega_i + omega_j  (sum เพราะ error ของ 2 stocks)
        → Ω = diag([...])
        ความหมาย: uncertainty = SVR model error จริงๆ

        Scale adjustment (สำคัญ — ทำเหมือน bl_model_port_optimization/05_BL_MODEL §5):
            raw_omega_abs = [omega_i for absolute views]
            raw_omega_rel = [omega_i + omega_j for relative views]

            alpha_abs = median(diag(tau_sigma)) / median(raw_omega_abs)
            alpha_rel = median([P[k] @ tau_sigma @ P[k].T for rel views k]) / median(raw_omega_rel)

            calibrated_omega_abs = raw_omega_abs * alpha_abs
            calibrated_omega_rel = raw_omega_rel * alpha_rel

    Mode 3: "blend"
        ผสม he-litterman กับ svr-residual:
            Ω_k = 0.5 × (he_litterman_k) + 0.5 × (svr_residual_calibrated_k)
        ความหมาย: ถ่วงน้ำหนักเท่ากันระหว่าง market structure กับ model error

    Output: {
        "stock_order": ["AAPL", "MSFT", ...],   # N stocks, fixed order
        "P": [[...], ...],                        # K×N list of lists
        "Q": [...],                               # K floats
        "omega": {
            "he-litterman": [...],                # K floats (diagonal of Ω)
            "svr-residual": [...],                # K floats
            "blend":        [...]                 # K floats
        },
        "n_absolute": int,   # = N
        "n_relative": int,   # = sectors with ≥ 2 stocks
        "sectors": {"AAPL": "Information Technology", ...}
    }
    """
```

#### 2.1.4 `generate_ml_views(tickers, tau, delta, epochs)` (main function)

```python
def generate_ml_views(tickers: list[str], tau: float = 0.05,
                       delta: float = 2.5, epochs: int = 30) -> dict:
    """
    Main entry point — เรียกจาก server.py endpoint

    Steps:
        1. fetch_features(tickers)
        2. train_lstm_svr() per ticker (sequential — ไม่ parallel เพราะ web server)
        3. กรอง success=True เท่านั้น
        4. คำนวณ sigma จาก daily returns ของ tickers ที่ success
           returns_df = close.pct_change().dropna() → align วันที่ร่วมกัน
           sigma = returns_df.cov().values * 252   (annualized)
        5. build_views(results, sigma, tau)

    Output (ส่งเป็น JSON กลับไป frontend): {
        "ok": True,
        "stock_order": [...],
        "P": [...],
        "Q": [...],
        "omega": { "he-litterman": [...], "svr-residual": [...], "blend": [...] },
        "n_absolute": int,
        "n_relative": int,
        "r_hats": {"AAPL": 0.08, ...},     # สำหรับ debug/display ใน UI
        "sectors": {"AAPL": "IT", ...},
        "errors": {"XYZ": "reason"}         # tickers ที่ train fail
    }
    """
```

---

### ส่วนที่ 2: `server.py` — เพิ่ม endpoint

เพิ่ม POST endpoint `/api/ml-views` เข้าไปใน `BLHandler`:

```python
def do_POST(self):
    parsed = urllib.parse.urlparse(self.path)
    if parsed.path == "/api/ml-views":
        self._handle_ml_views()
    else:
        self.send_response(405)
        self.end_headers()

def _handle_ml_views(self):
    """
    POST /api/ml-views
    Body (JSON): {
        "tickers": ["AAPL", "MSFT", ...],
        "tau":     0.05,     (optional, default 0.05)
        "delta":   2.5,      (optional, default 2.5)
        "epochs":  30        (optional, default 30)
    }

    Response (JSON): output ของ generate_ml_views()

    Notes:
    - อ่าน Content-Length แล้ว parse JSON body
    - ถ้า tickers ว่าง → ส่ง error 400
    - ถ้า torch/sklearn ไม่ได้ติดตั้ง → ส่ง error 500 พร้อมข้อความ
      "torch and scikit-learn required: pip install torch scikit-learn pandas-ta"
    - log progress ใน terminal เหมือน /api/data เดิม
    - ใส่ Access-Control-Allow-Origin: * เหมือน endpoint อื่น
    - ต้องมี do_OPTIONS ด้วยสำหรับ CORS preflight:
        OPTIONS /api/ml-views → 200 + CORS headers
    """
```

---

### ส่วนที่ 3: `app.js` — เพิ่ม ML Views UI

#### 3.1 เพิ่มใน state

```javascript
// ใน state object เพิ่ม:
mlOmegaMode: 'he-litterman',   // 'he-litterman' | 'svr-residual' | 'blend'
mlLoading: false,
```

#### 3.2 เพิ่มปุ่มและ dropdown ใน Views tab

ตรงที่มีปุ่ม `#gen-auto` อยู่แล้ว ให้เพิ่มถัดจากนั้น:

```html
<!-- เพิ่มถัดจากปุ่ม gen-auto -->
<select id="ml-omega-mode">
  <option value="he-litterman">Ω: He-Litterman</option>
  <option value="svr-residual">Ω: SVR Residual</option>
  <option value="blend">Ω: Blend (50/50)</option>
</select>
<button id="gen-ml" class="btn-secondary">🤖 Generate ML Views</button>
<span id="ml-status" class="muted"></span>
```

#### 3.3 Event handler `#gen-ml`

```javascript
$('#gen-ml').addEventListener('click', async () => {
    /*
    1. ตรวจ state.market มีไหม → ถ้าไม่มีให้ alert "ดึงข้อมูลตลาดในหน้า Setup ก่อน"
    2. แสดง loading: $('#ml-status').textContent = "⏳ Training LSTM+SVR..."
    3. เปลี่ยน state.mlLoading = true, disable ปุ่ม

    4. POST /api/ml-views พร้อม body:
       {
         tickers: state.market.tickers,
         tau:     +tauEl.value,
         delta:   +deltaEl.value,
         epochs:  30
       }

    5. รอ response (อาจนาน 1-5 นาทีขึ้นกับจำนวนหุ้น)

    6. ถ้า ok: แปลง P, Q, omega[selected_mode] เป็น views แล้ว push เข้า state.views

    7. ถ้า error: แสดง alert พร้อม error message

    8. reset loading state, renderViews()
    */
});

$('#ml-omega-mode').addEventListener('change', (e) => {
    state.mlOmegaMode = e.target.value;
});
```

#### 3.4 ฟังก์ชัน `parseMLViews(mlData, omegaMode)`

```javascript
function parseMLViews(mlData, omegaMode) {
    /*
    แปลง response จาก /api/ml-views เป็น views[] สำหรับ state.views

    Input:
        mlData:    response JSON จาก backend
        omegaMode: 'he-litterman' | 'svr-residual' | 'blend'

    Process:
        stock_order = mlData.stock_order   // ["AAPL", "MSFT", ...]
        P           = mlData.P             // K×N array
        Q           = mlData.Q             // K floats
        omega_arr   = mlData.omega[omegaMode]  // K floats

        แปลงแต่ละ row ของ P เป็น view object:

        for k in range(K):
            p_row = P[k]                   // length N
            picks = {}
            stock_order.forEach((t, i) => {
                if (p_row[i] !== 0) picks[t] = p_row[i]
            })
            // ถ้า p_row มีแค่ค่า +1 → absolute view
            // ถ้า p_row มีทั้ง +1 และ -1 → relative view
            type = p_row.some(x => x < 0) ? 'relative' : 'absolute'

            views.push({
                id:      state.nextViewId++,
                enabled: true,
                type:    type,
                picks:   picks,
                q:       round(Q[k]),
                omega:   omega_arr[k]
            })

    Return: views[]  (push เข้า state.views)

    Note:
    - Q จาก ML เป็น 63-day return (~0.05-0.15) ไม่ต้อง capQ เพราะ
      SVR residual calibrated แล้ว แต่ถ้าค่า > 0.30 หรือ < -0.30
      ให้ clamp ป้องกัน extreme case
    - omega จาก backend ถูก scale แล้ว ไม่ต้องปรับอีก
    */
}
```

---

### ส่วนที่ 4: `index.html` — เพิ่ม HTML elements

ค้นหา element ที่มี id `gen-auto` แล้วเพิ่ม HTML ถัดจากนั้น:

```html
<!-- ถัดจาก #gen-auto group -->
<div class="ml-view-controls" style="margin-top: 12px; display: flex; gap: 8px; align-items: center;">
  <select id="ml-omega-mode" class="input-sm">
    <option value="he-litterman">Ω: He-Litterman</option>
    <option value="svr-residual">Ω: SVR Residual</option>
    <option value="blend">Ω: Blend (50/50)</option>
  </select>
  <button id="gen-ml" class="btn btn-secondary">🤖 ML Views</button>
  <span id="ml-status" style="font-size: 0.85em; color: #888;"></span>
</div>
```

---

## 3. Dependencies ที่ต้องติดตั้ง

```bash
pip install torch scikit-learn pandas-ta numpy pandas yfinance
# TA-Lib (optional สำหรับ Hilbert Transform):
# conda install -c conda-forge ta-lib  หรือ
# pip install TA-Lib  (ต้องติดตั้ง C library ก่อน)
```

ถ้าไม่มี TA-Lib → ht_dcperiod = 0.0 และ log warning — ไม่ crash

---

## 4. Data Flow สรุป

```
User กด "🤖 ML Views"
    ↓
app.js: POST /api/ml-views { tickers, tau, delta, epochs }
    ↓
server.py: _handle_ml_views()
    ↓
ml_views.py: generate_ml_views()
    ├─ fetch_features() → OHLCV + 8 indicators per ticker
    ├─ train_lstm_svr() per ticker → r̂, ω
    ├─ compute sigma (annualized covariance)
    └─ build_views() → P, Q, Ω×3
    ↓
JSON response → app.js: parseMLViews()
    ↓
state.views.push(...) → renderViews()
    ↓
User กด "Run BL" → BL engine เดิมทำงานต่อ (ไม่ต้องแก้)
```

---

## 5. สิ่งที่ห้ามแตะ

- `engine/blacklitterman.js` — ไม่แก้เลย
- `engine/matrix.js` — ไม่แก้เลย
- `engine/stats.js` — ไม่แก้เลย
- manual view และ auto-signal view เดิม — ยังคงใช้งานได้ตามปกติ
- `/api/data` endpoint — ไม่แก้

---

## 6. Edge Cases ที่ต้องจัดการ

| กรณี | วิธีจัดการ |
|---|---|
| ticker ดึงข้อมูลไม่ได้ | skip, log ใน errors, train ต่อด้วยที่เหลือ |
| torch ไม่ได้ติดตั้ง | ส่ง error 500 พร้อมข้อความ install |
| sector มีแค่ 1 stock | สร้างแค่ absolute view ไม่มี relative |
| r̂ > 0.30 หรือ < -0.30 | clamp ใน parseMLViews() |
| omega ออกมาเป็น 0 | ใส่ fallback = 1e-6 เพื่อป้องกัน Ω singular |
| ทุก ticker fail | ส่ง error "no stocks trained successfully" |
| request timeout | epochs ต่ำ (default 30) ทำให้เร็วพอสำหรับ web |

---

## 7. ลำดับ implement แนะนำ

1. `backend/ml_views.py` — เขียนและทดสอบแยกก่อน
2. `server.py` — เพิ่ม endpoint และทดสอบด้วย curl
3. `index.html` — เพิ่ม HTML elements
4. `app.js` — เพิ่ม event handler และ parseMLViews()
5. ทดสอบ end-to-end กับ 3-5 stocks ก่อน

---

## 8. ทดสอบ endpoint ด้วย curl

```bash
# ทดสอบ endpoint โดยตรง (หลัง server รัน):
curl -X POST http://localhost:8770/api/ml-views \
  -H "Content-Type: application/json" \
  -d '{"tickers": ["AAPL", "MSFT", "GOOGL"], "tau": 0.05, "delta": 2.5, "epochs": 5}'

# ผลที่ควรได้:
# { "ok": true, "stock_order": [...], "P": [...], "Q": [...], "omega": {...}, ... }
```
