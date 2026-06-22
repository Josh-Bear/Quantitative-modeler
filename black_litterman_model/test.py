import numpy as np

np.set_printoptions(precision=4, suppress=True)

# ══════════════════════════════════════════════════════════════
# STEP 1: ข้อมูลตั้งต้น
# ══════════════════════════════════════════════════════════════

stocks = ['PTT', 'AOT', 'KBANK', 'CPF']

# Market Cap (ล้านบาท)
market_cap = np.array([900_000, 600_000, 300_000, 200_000])
w_mkt = market_cap / market_cap.sum()

# Covariance Matrix
sigma = np.array([
    [0.0400, 0.0100, 0.0080, 0.0050],
    [0.0100, 0.0625, 0.0060, 0.0040],
    [0.0080, 0.0060, 0.0900, 0.0070],
    [0.0050, 0.0040, 0.0070, 0.1600],
])

delta = 3.0   # Risk aversion
tau   = 0.05  # Uncertainty of prior

# ══════════════════════════════════════════════════════════════
# STEP 2: คำนวณ Π (Prior)
# ══════════════════════════════════════════════════════════════

pi = delta * sigma @ w_mkt  # @ คือ matrix multiplication

# ══════════════════════════════════════════════════════════════
# STEP 3: กำหนด Views
# ══════════════════════════════════════════════════════════════

# P = Pick Matrix (3 views × 4 stocks)
P = np.array([
    [1,  0,    0,    0  ],  # View 1: PTT ได้ 12% (Absolute)
    [0,  1,   -1,    0  ],  # View 2: AOT outperform KBANK 4% (Relative)
    [1,  0,   -0.5, -0.5],  # View 3: PTT outperform KBANK+CPF 2% (Relative)
])

# Q = Expected returns จาก views
Q = np.array([0.12, 0.04, 0.02])

# Omega = Diagonal matrix ความไม่แน่นอนของ views
omega = np.diag([0.0010, 0.0005, 0.0020])

# ══════════════════════════════════════════════════════════════
# STEP 4: Bayesian Update → μ_BL
# ══════════════════════════════════════════════════════════════

# Inverse ของ (τΣ)
tau_sigma_inv = np.linalg.inv(tau * sigma)

# Inverse ของ Ω
omega_inv = np.linalg.inv(omega)

# M = Posterior Variance
M = np.linalg.inv(tau_sigma_inv + P.T @ omega_inv @ P)

# μ_BL = Posterior Returns
mu_bl = M @ (tau_sigma_inv @ pi + P.T @ omega_inv @ Q)

# ══════════════════════════════════════════════════════════════
# STEP 5: Optimal Weights
# ══════════════════════════════════════════════════════════════

sigma_bl = sigma + M
w_star = np.linalg.inv(delta * sigma_bl) @ mu_bl
w_star = w_star / w_star.sum()  # normalize ให้รวมเป็น 1

# ══════════════════════════════════════════════════════════════
# แสดงผล
# ══════════════════════════════════════════════════════════════

print("=" * 55)
print("  BLACK-LITTERMAN MODEL — หุ้นไทย 4 ตัว")
print("=" * 55)

print("\n📌 STEP 1: Market Weights (w_mkt)")
print("-" * 40)
for s, w in zip(stocks, w_mkt):
    print(f"  {s:<8} {w:.2%}")

print("\n📌 STEP 2: Implied Returns (Π)")
print("-" * 40)
for s, p in zip(stocks, pi):
    print(f"  {s:<8} {p:.2%}")

print("\n📌 STEP 3: Views")
print("-" * 40)
print("  View 1 (Absolute):  PTT = 12.00%")
print("  View 2 (Relative):  AOT > KBANK by 4.00%")
print("  View 3 (Relative):  PTT > (KBANK+CPF) by 2.00%")

print("\n📌 STEP 4: BL Posterior Returns (μ_BL)")
print("-" * 55)
print(f"  {'หุ้น':<8} {'Π (Prior)':>12} {'μ_BL':>12} {'เปลี่ยน':>10}")
print("  " + "-" * 48)
for s, p, m in zip(stocks, pi, mu_bl):
    diff = m - p
    arrow = "↑" if diff > 0 else "↓"
    print(f"  {s:<8} {p:>11.2%} {m:>11.2%} {diff:>+9.2%} {arrow}")

print("\n📌 STEP 5: Optimal Portfolio Weights")
print("-" * 55)
print(f"  {'หุ้น':<8} {'w_mkt':>12} {'w* (BL)':>12} {'เปลี่ยน':>10}")
print("  " + "-" * 48)
for s, wm, ws in zip(stocks, w_mkt, w_star):
    diff = ws - wm
    arrow = "↑" if diff > 0 else "↓"
    print(f"  {s:<8} {wm:>11.2%} {ws:>11.2%} {diff:>+9.2%} {arrow}")

print("\n" + "=" * 55)
print("  สรุป: BL ดึง PTT ขึ้นมากสุด เพราะ View 1 + View 3 เชียร์พร้อมกัน")
print("        KBANK ลดลงชัดเจน เพราะ View 2 และ View 3 กดลง")
print("        CPF เพิ่มขึ้นเล็กน้อย — correlation effect ชนะ View 3 ที่อ่อน")
print("=" * 55)