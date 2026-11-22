"""
pretrade.py — turn signals into parent-order requests and enforce pre-trade rules.

Checks, in order (every reject / adjustment is written to the log):
  1. WEIGHT_BOUNDS   target weight clipped to [W_MIN, W_MAX]
  2. ZERO_LOT        Δshares rounded toward zero to board lots (away from zero when
                     the order exists to get back inside a bound); 0 lots → no order
  3. NO_SHORT        sell ≤ shares held
  4. MIN_NOTIONAL    order value ≥ MIN_ORDER_THB
  5. CASH            sells first; buys scaled down pro-rata to the cash projected
                     after sells and after cash already reserved by open orders
                     (settlement assumed immediate — no T+2)
  6. ACTIVE_ORDER    one open parent order per ticker; new signals are skipped
  7. POST_TRADE      projected weights re-checked against the bounds (warning)

Signal → target weight:  BUY w+Δw, SELL w−Δw, HOLD only rebalances a weight
that has drifted outside [W_MIN − REBAL_BAND, W_MAX + REBAL_BAND] back to the
nearest bound.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import constants as C
from .cost_model import half_spread
from .market_rules import ceil_lot, floor_lot
from .signals import BUY, HOLD, SELL

EPS = 1e-9


@dataclass
class OrderRequest:
    ticker: str
    side: int            # +1 buy, -1 sell
    qty: int             # shares, > 0, multiple of LOT
    reason: str          # SIGNAL_BUY | SIGNAL_SELL | REBAL_MAX | REBAL_MIN
    current_w: float
    target_w: float


def _log(log, dt, strategy, ticker, check, action, detail, before=None, after=None):
    log.append({"datetime": dt, "strategy": strategy, "ticker": ticker, "check": check,
                "action": action, "detail": detail, "qty_before": before, "qty_after": after})


def _est_unit_cost(price: float) -> float:
    return half_spread(price) + price * C.COMMISSION_ALL_IN


def generate_orders(dt, strategy: str, tickers: list[str], prices: dict[str, float],
                    sig_code: dict[str, int], dw: dict[str, float], holdings: dict[str, int],
                    cash: float, open_remaining: dict[str, int], log: list) -> list[OrderRequest]:
    """open_remaining: ticker → signed shares still to trade on its open parent order."""
    nav = cash + sum(holdings[t] * prices[t] for t in tickers)
    sells: list[OrderRequest] = []
    buys: list[OrderRequest] = []

    for t in tickers:
        p, h, code = prices[t], holdings[t], sig_code[t]
        w = h * p / nav
        if code == BUY:
            target, reason = w + dw[t], "SIGNAL_BUY"
        elif code == SELL:
            target, reason = w - dw[t], "SIGNAL_SELL"
        elif w > C.W_MAX + C.REBAL_BAND:
            target, reason = C.W_MAX, "REBAL_MAX"
        elif w < C.W_MIN - C.REBAL_BAND:
            target, reason = C.W_MIN, "REBAL_MIN"
        else:
            continue

        if t in open_remaining:                                         # 6
            _log(log, dt, strategy, t, "ACTIVE_ORDER", "REJECT",
                 f"{reason} skipped: open order still has {open_remaining[t]:+d} shares")
            continue

        clipped = min(max(target, C.W_MIN), C.W_MAX)                     # 1
        if abs(clipped - target) > EPS:
            _log(log, dt, strategy, t, "WEIGHT_BOUNDS", "ADJUST",
                 f"{reason} target {target:.2%} → {clipped:.2%}")

        raw = (clipped - w) * nav / p                                    # 2
        # normally round toward zero; but when the order exists to get back inside
        # a bound, round away from zero so the result actually lands inside it
        back_inside = (w > C.W_MAX and raw < 0) or (w < C.W_MIN and raw > 0)
        qty = ceil_lot(raw) if back_inside else floor_lot(raw)
        if qty == 0:
            _log(log, dt, strategy, t, "ZERO_LOT", "REJECT",
                 f"{reason} Δw {clipped - w:+.2%} < 1 lot")
            continue

        if qty < 0 and -qty > h:                                         # 3
            _log(log, dt, strategy, t, "NO_SHORT", "ADJUST", f"sell capped at holdings {h}", -qty, h)
            qty = -h
            if qty == 0:
                continue

        if abs(qty) * p < C.MIN_ORDER_THB:                               # 4
            _log(log, dt, strategy, t, "MIN_NOTIONAL", "REJECT",
                 f"{reason} {abs(qty) * p:,.0f} THB < {C.MIN_ORDER_THB:,.0f}", abs(qty), 0)
            continue

        req = OrderRequest(t, 1 if qty > 0 else -1, abs(qty), reason, w, clipped)
        (buys if qty > 0 else sells).append(req)

    # 5 — cash: projected cash after sells and after what open orders already reserve
    avail = cash
    for t, rem in open_remaining.items():
        p = prices[t]
        avail += -rem * p - abs(rem) * _est_unit_cost(p)
    for s in sells:
        avail += s.qty * (prices[s.ticker] - _est_unit_cost(prices[s.ticker]))
    need = sum(b.qty * (prices[b.ticker] + _est_unit_cost(prices[b.ticker])) for b in buys)
    if buys and need > avail + EPS:
        scale = max(avail, 0.0) / need
        kept = []
        for b in buys:
            new_qty = floor_lot(b.qty * scale)
            p = prices[b.ticker]
            if new_qty == 0 or new_qty * p < C.MIN_ORDER_THB:
                _log(log, dt, strategy, b.ticker, "CASH", "REJECT",
                     f"need {need:,.0f} THB, available {avail:,.0f} (scale {scale:.2f})", b.qty, 0)
                continue
            _log(log, dt, strategy, b.ticker, "CASH", "ADJUST",
                 f"buy scaled ×{scale:.2f} to fit cash", b.qty, new_qty)
            b.qty = new_qty
            kept.append(b)
        buys = kept

    # 7 — post-trade weight check (warning only)
    proj = dict(holdings)
    for r in sells + buys:
        proj[r.ticker] += r.side * r.qty
    for r in sells + buys:
        w_new = proj[r.ticker] * prices[r.ticker] / nav
        if w_new > C.W_MAX + 1e-4 or w_new < C.W_MIN - 1e-4:
            _log(log, dt, strategy, r.ticker, "POST_TRADE", "WARN",
                 f"projected weight {w_new:.2%} outside [{C.W_MIN:.0%}, {C.W_MAX:.0%}]")

    return sells + buys       # sells first so their cash funds the buys
