"""market_rules.py — SET tick sizes and board-lot rounding."""
from __future__ import annotations

import math

from . import constants as C


def tick_size(price: float) -> float:
    for bound, tick in C.SET_TICK_TABLE:
        if price < bound:
            return tick
    return C.SET_TICK_TABLE[-1][1]


def round_to_tick(price: float, mode: str = "nearest") -> float:
    """Snap a price onto the SET grid ('nearest' | 'up' | 'down')."""
    tick = tick_size(price)
    steps = price / tick
    if mode == "up":
        steps = math.ceil(steps - 1e-9)
    elif mode == "down":
        steps = math.floor(steps + 1e-9)
    else:
        steps = round(steps)
    return round(steps * tick, 6)


def floor_lot(shares: float, lot: int = C.LOT) -> int:
    """Round |shares| down to whole board lots, keeping the sign."""
    if shares != shares:  # NaN
        return 0
    lots = math.floor(abs(shares) / lot + 1e-9)
    return int(math.copysign(lots * lot, shares)) if lots else 0


def ceil_lot(shares: float, lot: int = C.LOT) -> int:
    """Round |shares| up to whole board lots, keeping the sign."""
    if shares != shares:
        return 0
    lots = math.ceil(abs(shares) / lot - 1e-9)
    return int(math.copysign(lots * lot, shares)) if lots else 0
