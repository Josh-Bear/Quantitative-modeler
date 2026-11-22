"""
cost_model.py — what a fill costs relative to the observed Close (treated as mid).

  exec_price = Close + side × (half_spread + impact)
  half_spread = SPREAD_TICKS × tick(Close) / 2
  impact      = IMPACT_Y × σ_hour × sqrt(child_notional / bar_value) × Close   (square-root law;
                bar_value = THB actually traded in that bar, from the data)
  commission  = exec_price × qty × COMMISSION × (1 + VAT)

The cost-inclusive price is NOT snapped to the tick grid: it represents the
average price of sweeping the book, which need not sit on a tick. Snapping
mid + ½ tick upward would silently charge a full tick instead of half.
"""
from __future__ import annotations

import math

from . import constants as C
from .market_rules import tick_size


def half_spread(price: float) -> float:
    return C.SPREAD_TICKS * tick_size(price) / 2.0


def impact(price: float, sigma: float, notional: float, bar_value: float) -> float:
    if notional <= 0 or bar_value <= 0 or sigma <= 0:
        return 0.0
    return C.IMPACT_Y * sigma * math.sqrt(notional / bar_value) * price


def fill_cost(price: float, side: int, qty: int, sigma: float, bar_value: float) -> dict:
    hs = half_spread(price)
    imp = impact(price, sigma, qty * price, bar_value)
    exec_price = price + side * (hs + imp)
    notional = exec_price * qty
    commission = notional * C.COMMISSION_ALL_IN
    return {"half_spread": hs, "impact": imp, "exec_price": exec_price,
            "notional": notional, "commission": commission,
            "cash_flow": -side * notional - commission}
