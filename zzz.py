
# pyrefly: ignore [parse-error]
import numpy as np


class ViewBuilder:
    def __init__(self, asset_names):
        """
        asset_names: list ของชื่อ/ticker หุ้นทั้งหมดใน universe
                     (จำนวนเท่าไหร่ก็ได้ ตาม user กรอก)
        """
        self.assets = list(asset_names)
        self.n = len(self.assets)
        self._idx = {name: i for i, name in enumerate(self.assets)}
        self.views = []  # เก็บ view แต่ละอันเป็น dict

    # ---------- เพิ่ม Absolute View ----------
    def add_absolute_view(self, asset, expected_return, confidence=None):
        """
        asset: ชื่อหุ้นหนึ่งตัว
        expected_return: ผลตอบแทนที่คาด (เช่น 0.08 = 8%)
        confidence: 0-1 (ความมั่นใจ, optional ถ้าจะใช้ He-Litterman แทน)
        """
        row = np.zeros(self.n)
        row[self._idx[asset]] = 1.0
        self.views.append({
            "type": "absolute",
            "P_row": row,
            "Q": expected_return,
            "confidence": confidence,
        })

    # ---------- เพิ่ม Relative View ----------
    def add_relative_view(self, outperform, underperform, expected_diff,
                           weight_scheme="equal", market_caps=None,
                           confidence=None):
        """
        outperform: list ของหุ้นฝั่งที่คาดว่าจะดีกว่า (1 ตัวหรือหลายตัวก็ได้)
        underperform: list ของหุ้นฝั่งที่คาดว่าจะแย่กว่า
        expected_diff: ส่วนต่างผลตอบแทนที่คาด (outperform - underperform)
        weight_scheme: "equal" หรือ "cap_weighted"
        market_caps: dict {asset: market_cap} จำเป็นถ้าใช้ cap_weighted
        confidence: 0-1
        """
        row = np.zeros(self.n)

        def _weights(group):
            if weight_scheme == "equal":
                w = 1.0 / len(group)
                return {a: w for a in group}
            elif weight_scheme == "cap_weighted":
                total = sum(market_caps[a] for a in group)
                return {a: market_caps[a] / total for a in group}
            else:
                raise ValueError("weight_scheme ต้องเป็น 'equal' หรือ 'cap_weighted'")

        for asset, w in _weights(outperform).items():
            row[self._idx[asset]] += w
        for asset, w in _weights(underperform).items():
            row[self._idx[asset]] -= w

        self.views.append({
            "type": "relative",
            "P_row": row,
            "Q": expected_diff,
            "confidence": confidence,
        })

    # ---------- Helper: สร้าง Q จากสัญญาณเชิงปริมาณ ----------
    @staticmethod
    def implied_return_from_target_price(current_price, target_price):
        """แปลง analyst target price เป็น absolute view return"""
        return target_price / current_price - 1.0

    @staticmethod
    def momentum_signal(price_series, lookback=252):
        """คืนค่า trailing return ใช้เป็น proxy ของ view return"""
        prices = np.asarray(price_series)
        return prices[-1] / prices[-lookback] - 1.0

    @staticmethod
    def valuation_gap(current_multiple, historical_avg_multiple):
        """ส่วนต่าง valuation เทียบค่าเฉลี่ยย้อนหลัง แปลงเป็น expected mean-reversion return"""
        return historical_avg_multiple / current_multiple - 1.0

    # ---------- Build P, Q, Omega ----------
    def build(self, tau, sigma, omega_method="he_litterman"):
        """
        tau: scalar (มักตั้ง 0.025-0.05)
        sigma: covariance matrix ของผลตอบแทน (n x n) ตามลำดับ self.assets
        omega_method: "he_litterman" | "idzorek" | "manual"

        คืนค่า P (k x n), Q (k,), Omega (k x k)
        """
        if not self.views:
            raise ValueError("ยังไม่มี view ที่เพิ่มเข้ามาเลย")

        P = np.vstack([v["P_row"] for v in self.views])
        Q = np.array([v["Q"] for v in self.views])
        sigma = np.asarray(sigma)

        if omega_method == "he_litterman":
            # Omega_ii = tau * (P_i Sigma P_i^T) -- ผูกกับ variance ของ view นั้นเอง
            omega_diag = np.array([
                tau * (P[i] @ sigma @ P[i].T) for i in range(len(self.views))
            ])

        elif omega_method == "idzorek":
            # ต้องมี confidence (0-1) ครบทุก view
            confidences = [v["confidence"] for v in self.views]
            if any(c is None for c in confidences):
                raise ValueError("ทุก view ต้องมี confidence (0-1) เมื่อใช้ omega_method='idzorek'")
            omega_diag = np.zeros(len(self.views))
            for i, c in enumerate(confidences):
                # variance เต็มที่ (confidence ต่ำสุด) จาก he-litterman baseline
                base_var = tau * (P[i] @ sigma @ P[i].T)
                c = np.clip(c, 1e-4, 1.0)  # กัน div-by-zero
                # confidence สูง -> variance ต่ำ (ใกล้ 0), confidence ต่ำ -> variance สูง
                omega_diag[i] = base_var * (1.0 / c - 1.0) if c < 1.0 else 1e-8

        elif omega_method == "manual":
            confidences = [v["confidence"] for v in self.views]
            if any(c is None for c in confidences):
                raise ValueError("ทุก view ต้องมี confidence เมื่อใช้ omega_method='manual'")
            # ตีความ confidence เป็น 1/variance โดยตรง (normalize เอง)
            omega_diag = np.array([
                (1.0 - c) * (P[i] @ sigma @ P[i].T) + 1e-8
                for i, c in enumerate(confidences)
            ])

        else:
            raise ValueError("omega_method ต้องเป็น 'he_litterman', 'idzorek' หรือ 'manual'")

        Omega = np.diag(omega_diag)
        return P, Q, Omega

    def summary(self):
        """แสดงสรุป views ทั้งหมดแบบอ่านง่าย"""
        lines = []
        for i, v in enumerate(self.views):
            involved = [
                f"{self.assets[j]}({v['P_row'][j]:+.2f})"
                for j in range(self.n) if v["P_row"][j] != 0
            ]
            lines.append(
                f"View {i+1} [{v['type']}]: {', '.join(involved)}  "
                f"Q={v['Q']:.4f}  conf={v['confidence']}"
            )
        return "\n".join(lines)


# ---------------- ตัวอย่างการใช้งาน ----------------
if __name__ == "__main__":
    # สมมติ user กรอกหุ้นมา 5 ตัว (จำนวนเท่าไหร่ก็ได้)
    assets = ["AAPL", "MSFT", "GOOG", "AMZN", "META"]
    n = len(assets)

    # covariance matrix ตัวอย่าง (จริงๆ ควรคำนวณจาก historical returns)
    np.random.seed(0)
    rand = np.random.randn(n, n)
    sigma = rand @ rand.T * 0.01  # ทำให้เป็น positive semi-definite

    builder = ViewBuilder(assets)

    # Absolute view: AAPL จะให้ผลตอบแทน 8% มั่นใจ 60%
    builder.add_absolute_view("AAPL", expected_return=0.08, confidence=0.6)

    # Relative view: MSFT จะดีกว่า GOOG อยู่ 3% มั่นใจ 50%
    builder.add_relative_view(
        outperform=["MSFT"], underperform=["GOOG"],
        expected_diff=0.03, confidence=0.5
    )

    # Relative view แบบ basket: (AMZN+META) ดีกว่า (AAPL) เฉลี่ย cap-weighted
    builder.add_relative_view(
        outperform=["AMZN", "META"], underperform=["AAPL"],
        expected_diff=0.02, weight_scheme="cap_weighted",
        market_caps={"AMZN": 1800, "META": 1200, "AAPL": 3000},
        confidence=0.4
    )

    print(builder.summary())
    print()

    P, Q, Omega = builder.build(tau=0.05, sigma=sigma, omega_method="idzorek")
    print("P =\n", P)
    print("Q =", Q)
    print("Omega =\n", Omega)