"""
execution.py — parent orders and the slicing executor.

An order decided at the close of bar t (arrival price = Close_t) starts
filling in the NEXT bar. Market and TWAP are the same mechanism with a
different slice count:
  MARKET  n_slices = 1 → whole order at Close_{t+1}
  TWAP    n_slices = N → equal board-lot slices over bars t+1 … t+N

Per bar a child fills at most PARTICIPATION_CAP × that bar's actual traded
value (and, for buys, what cash can pay for); a bar with no trading fills
nothing. What a slice cannot fill is carried to the next
slice; whatever is still unfilled after the last slice is cancelled (it shows up
as opportunity cost in the metrics).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import constants as C
from .cost_model import fill_cost
from .market_rules import floor_lot


def split_lots(qty: int, n: int, lot: int = C.LOT) -> list[int]:
    """Split qty (a multiple of lot) into n near-equal lot multiples, larger first."""
    lots = qty // lot
    base, extra = divmod(lots, n)
    return [(base + (1 if k < extra else 0)) * lot for k in range(n)]


@dataclass
class ParentOrder:
    order_id: int
    strategy: str
    ticker: str
    side: int
    qty: int
    reason: str
    arrival_i: int
    arrival_dt: object
    arrival_price: float
    current_w: float
    target_w: float
    n_slices: int
    schedule: list[int] = field(default_factory=list)
    filled: int = 0
    cancelled: int = 0
    carry: int = 0
    status: str = "OPEN"
    cancel_price: float | None = None
    cancel_reason: str = ""
    last_fill_i: int | None = None
    end_i: int | None = None

    def __post_init__(self):
        if not self.schedule:
            self.schedule = split_lots(self.qty, self.n_slices)

    @property
    def remaining(self) -> int:
        return self.qty - self.filled - self.cancelled

    def cancel(self, i: int, price: float, reason: str):
        self.cancelled += self.remaining
        self.carry = 0
        self.cancel_price = price
        self.cancel_reason = reason
        self.status = "DONE"
        self.end_i = i


def execute_bar(order: ParentOrder, i: int, dt, price: float, sigma: float,
                cash: float, bar_value: float) -> dict | None:
    """Work the order for bar i (> arrival bar). Returns a fill record (or None). Mutates order."""
    if order.status != "OPEN" or i <= order.arrival_i:
        return None
    k = i - order.arrival_i - 1          # slice index: 0 in the bar after arrival
    last_slice = k >= order.n_slices - 1
    want = order.carry + (order.schedule[k] if k < order.n_slices else 0)
    want = min(want, order.remaining)

    fill = None
    if want > 0:
        q = min(want, floor_lot(C.PARTICIPATION_CAP * bar_value / price))
        limit_note = "cap" if q < want else ""
        if order.side > 0 and q > 0:
            probe = fill_cost(price, 1, q, sigma, bar_value)
            unit = (probe["notional"] + probe["commission"]) / q
            affordable = floor_lot(max(cash, 0.0) / unit)
            if affordable < q:
                q, limit_note = affordable, "cash"
        if q > 0:
            c = fill_cost(price, order.side, q, sigma, bar_value)
            order.filled += q
            order.last_fill_i = i
            fill = {"order_id": order.order_id, "strategy": order.strategy, "ticker": order.ticker,
                    "side": "BUY" if order.side > 0 else "SELL", "bar": i, "datetime": dt,
                    "slice": k + 1, "qty": q, "mid": price, "half_spread": c["half_spread"],
                    "impact": c["impact"], "exec_price": c["exec_price"], "notional": c["notional"],
                    "commission": c["commission"], "cash_flow": c["cash_flow"],
                    "bar_value": bar_value, "participation": c["notional"] / bar_value,
                    "limited_by": limit_note}
        order.carry = want - q

    if order.remaining == 0:
        order.status, order.end_i = "DONE", i
    elif last_slice:
        order.cancel(i, price, "unfilled after last slice")
    return fill
