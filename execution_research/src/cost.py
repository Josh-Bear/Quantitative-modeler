"""
cost.py — what one child fill costs, relative to the bar VWAP.

  exec_price  = bar_vwap + side × (half_spread + impact)
  half_spread = spread_ticks × tick(bar_vwap) / 2
  impact      = Y × σ_hour × sqrt(child_notional / bar_traded_value) × bar_vwap   (square-root law)
  commission  = exec_price × qty × COMMISSION × (1 + VAT)

The cost-inclusive price is not snapped to the tick grid: it is an average
price, and snapping vwap + ½ tick upward would silently charge a full tick.
Impact is temporary (it does not carry into later bars).
"""
from __future__ import annotations

import math

from . import constants as C


def tick_size(price: float) -> float:
    for bound, tick in C.SET_TICK_TABLE:
        if price < bound:
            return tick
    return C.SET_TICK_TABLE[-1][1]


def floor_lot(shares: float, lot: int = C.LOT) -> int:
    if not shares > 0:          # also catches NaN
        return 0
    return int(math.floor(shares / lot + 1e-9)) * lot


def half_spread(price: float, spread_ticks: float) -> float:
    return spread_ticks * tick_size(price) / 2.0


def impact(price: float, sigma: float, notional: float, bar_value: float, y: float) -> float:
    if notional <= 0 or bar_value <= 0 or not sigma > 0:
        return 0.0
    return y * sigma * math.sqrt(notional / bar_value) * price


def fill(price: float, side: int, qty: int, sigma: float, bar_value: float,
         spread_ticks: float, y: float) -> dict:
    hs = half_spread(price, spread_ticks)
    imp = impact(price, sigma, qty * price, bar_value, y)
    exec_price = price + side * (hs + imp)
    notional = exec_price * qty
    return {"half_spread": hs, "impact": imp, "exec_price": exec_price, "notional": notional,
            "commission": notional * C.COMMISSION_ALL_IN}
