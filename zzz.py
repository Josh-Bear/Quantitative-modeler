import numpy as np
import pandas as pd

np.set_printoptions(precision=4, suppress=True)

# ══════════════════════════════════════════════════════
# MOCK DATA — ใช้ข้อมูลสมมติ (เพราะ yfinance ใช้ไม่ได้)
# ในชีวิตจริงแทนด้วย yf.download(tickers, interval="1mo")
# ══════════════════════════════════════════════════════

np.random.seed(42)

TICKERS = ["NVDA", "AAPL", "MSFT", "GOOGL"]
N = len(TICKERS)
T_TOTAL = 60  # 5 ปี รายเดือน

# สร้าง returns สมมติที่สมเหตุสมผล
# NVDA: return สูง vol สูง | AAPL/MSFT/GOOGL: return ปานกลาง
true_means   = np.array([0.025, 0.012, 0.010, 0.015])  # monthly
true_vol     = np.array([0.120, 0.065, 0.070, 0.085])  # monthly vol
corr = np.array([
    [1.00, 0.45, 0.42, 0.48],
    [0.45, 1.00, 0.75, 0.70],
    [0.42, 0.75, 1.00, 0.68],
    [0.48, 0.70, 0.68, 1.00],
])
cov_monthly = np.diag(true_vol) @ corr @ np.diag(true_vol)

# simulate returns
returns_all = np.random.multivariate_normal(true_means, cov_monthly, T_TOTAL)
# shape: (60, 4) — 60 เดือน, 4 หุ้น

# ── Train / Test Split ────────────────────────────────
TRAIN_END = 36   # 3 ปีแรก = train
# Test = ปีที่ 4–5

returns_train = returns_all[:TRAIN_END]   # (36, 4)
returns_test  = returns_all[TRAIN_END:]   # (24, 4)

print("=" * 60)
print("  BL COMPARISON: 3 แบบ w_mkt")
print(f"  Train: {TRAIN_END} เดือน | Test: {T_TOTAL-TRAIN_END} เดือน")
print("=" * 60)

# ══════════════════════════════════════════════════════
# MATH UTILITIES
# ══════════════════════════════════════════════════════

def compute_cov(returns):
    """Sample covariance matrix"""
    return np.cov(returns.T)  # (N, N)

def mat_inv(A):
    return np.linalg.inv(A)

def run_bl(sigma, w_mkt, delta, tau, P=None, Q=None, Omega=None):
    """BL model — return mu_bl, w_star"""
    Pi = delta * sigma @ w_mkt

    if P is None:
        # ไม่มี views — w* = w_mkt
        return Pi, w_mkt.copy()

    tau_sig_inv = mat_inv(tau * sigma)
    omega_inv   = mat_inv(Omega)

    M    = mat_inv(tau_sig_inv + P.T @ omega_inv @ P)
    rhs  = tau_sig_inv @ Pi + P.T @ omega_inv @ Q
    mu_bl = M @ rhs

    sigma_bl = sigma + M
    w_raw    = mat_inv(delta * sigma_bl) @ mu_bl

    # Long-only + normalize
    w_raw = np.maximum(w_raw, 0)
    w_sum = w_raw.sum()
    if w_sum < 1e-8:
        return mu_bl, w_mkt.copy()
    return mu_bl, w_raw / w_sum

def portfolio_metrics(weights, returns_test, rf_monthly=0.004):
    """คำนวณ Sharpe, Return, Vol จาก test set"""
    port_returns = returns_test @ weights          # (T_test,)
    mean_r  = port_returns.mean()
    std_r   = port_returns.std()
    sharpe  = (mean_r - rf_monthly) / std_r * np.sqrt(12)  # annualized
    ann_ret = (1 + mean_r) ** 12 - 1
    ann_vol = std_r * np.sqrt(12)
    return ann_ret, ann_vol, sharpe

# ══════════════════════════════════════════════════════
# คำนวณ Σ จาก train set
# ══════════════════════════════════════════════════════

sigma = compute_cov(returns_train)
delta = 3.0
tau   = 0.05

# ══════════════════════════════════════════════════════
# 3 แบบของ w_mkt
# ══════════════════════════════════════════════════════

# สมมติ Market Cap (ล้านล้าน USD)
market_caps = np.array([5.10, 3.20, 2.81, 4.44])

# แบบที่ 1: Market Cap Weighted
w_mkt_cap = market_caps / market_caps.sum()

# แบบที่ 2: Equal Weighted
w_mkt_equal = np.ones(N) / N

# แบบที่ 3: Volatility Weighted (inverse vol)
train_vols = returns_train.std(axis=0)
inv_vol    = 1.0 / train_vols
w_mkt_vol  = inv_vol / inv_vol.sum()

print("\n📌 w_mkt แต่ละแบบ")
print("-" * 55)
print(f"{'Ticker':<10}", end="")
for t in TICKERS:
    print(f"{t:>10}", end="")
print()
print(f"{'Market Cap':<10}", end="")
for w in w_mkt_cap:
    print(f"{w:>10.1%}", end="")
print()
print(f"{'Equal':<10}", end="")
for w in w_mkt_equal:
    print(f"{w:>10.1%}", end="")
print()
print(f"{'Vol Inv':<10}", end="")
for w in w_mkt_vol:
    print(f"{w:>10.1%}", end="")
print()

# ══════════════════════════════════════════════════════
# Views (เหมือนกันทุกแบบ เพื่อให้เปรียบยุติธรรม)
# ══════════════════════════════════════════════════════
# View 1: NVDA จะ outperform MSFT ด้วย 5% ต่อปี
# View 2: GOOGL จะได้ผลตอบแทน 18% ต่อปี

P = np.array([
    [ 1,  0, -1,  0],   # NVDA > MSFT
    [ 0,  0,  0,  1],   # GOOGL absolute
])
Q = np.array([0.05/12, 0.18/12])  # monthly
Omega = np.diag([0.001, 0.0005])

# ══════════════════════════════════════════════════════
# รัน BL ทั้ง 3 แบบ
# ══════════════════════════════════════════════════════

configs = [
    ("Market Cap", w_mkt_cap),
    ("Equal",      w_mkt_equal),
    ("Vol Inv",    w_mkt_vol),
]

results = {}

print("\n📌 Implied Returns Π (annualized)")
print("-" * 55)
print(f"{'':15}", end="")
for t in TICKERS:
    print(f"{t:>10}", end="")
print()

for name, w_mkt in configs:
    Pi = delta * sigma @ w_mkt
    print(f"{name:<15}", end="")
    for p in Pi:
        print(f"{p*12:>10.1%}", end="")   # annualize
    print()

print("\n📌 Optimal Weights w* (หลัง BL + Views)")
print("-" * 55)
print(f"{'':15}", end="")
for t in TICKERS:
    print(f"{t:>10}", end="")
print()

for name, w_mkt in configs:
    mu_bl, w_star = run_bl(sigma, w_mkt, delta, tau, P, Q, Omega)
    results[name] = w_star
    print(f"{name:<15}", end="")
    for w in w_star:
        print(f"{w:>10.1%}", end="")
    print()

# ══════════════════════════════════════════════════════
# TEST SET PERFORMANCE
# ══════════════════════════════════════════════════════

print("\n📌 TEST SET PERFORMANCE (ปีที่ 4–5)")
print("-" * 55)
print(f"{'Strategy':<15} {'Ann.Return':>12} {'Ann.Vol':>10} {'Sharpe':>10}")
print("  " + "-" * 48)

# Benchmark: ถือ Market Cap weighted โดยไม่มี BL
_, w_bench = run_bl(sigma, w_mkt_cap, delta, tau)  # no views
r, v, s = portfolio_metrics(w_bench, returns_test)
print(f"{'Benchmark':15} {r:>12.2%} {v:>10.2%} {s:>10.2f}  (w_mkt no views)")

for name, w_star in results.items():
    r, v, s = portfolio_metrics(w_star, returns_test)
    print(f"{name:<15} {r:>12.2%} {v:>10.2%} {s:>10.2f}")

# ══════════════════════════════════════════════════════
# SENSITIVITY: Views มีผลมากแค่ไหนเทียบกับ w_mkt?
# ══════════════════════════════════════════════════════

print("\n📌 SENSITIVITY — Views vs w_mkt")
print("   ถ้าเอา Views ออก w* เปลี่ยนมากแค่ไหน?")
print("-" * 55)

for name, w_mkt in configs:
    _, w_with_views    = run_bl(sigma, w_mkt, delta, tau, P, Q, Omega)
    _, w_without_views = run_bl(sigma, w_mkt, delta, tau)
    diff = np.abs(w_with_views - w_without_views).max()
    print(f"  {name:<15} max weight change: {diff:.1%}")

# ══════════════════════════════════════════════════════
# สรุป
# ══════════════════════════════════════════════════════

print("\n" + "=" * 60)
print("  KEY TAKEAWAYS")
print("=" * 60)
print("""
  1. Π ต่างกันตาม w_mkt — แต่ Views ดึง w* ให้ใกล้กัน
  2. Views มีผลต่อ w* มากกว่าการเลือก w_mkt
  3. Test set นี้ใช้ data สมมติ — ในชีวิตจริงแทนด้วย
     yf.download(tickers, period='5y', interval='1mo')
  4. ไม่มีแบบไหน 'ดีที่สุดเสมอ' — ขึ้นกับ period ที่ test
""")