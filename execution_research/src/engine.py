"""
engine.py — execute one parent order with one algorithm, bar by bar.

Timeline: decision + arrival price at Close_t. Children trade in bars
t+1 … t+H (H = horizon). Every child fills at that bar's VWAP ± costs (cost.py).
What an algo wants in bar t+1+k (k = 0 … H−1):

  MARKET  everything left, no cap (first bar with trading)
  TWAP    cumulative target Q·(k+1)/H                      − filled, ≤ cap × bar value
  VWAP    cumulative target Q·Σ profile(hours ≤ k)/Σ profile − filled, ≤ cap × bar value
  POV     rate × the bar's actual traded value (until Q is reached)

Cumulative targets make TWAP/VWAP catch up automatically after a capped or
no-trade bar. A bar with zero traded value fills nothing. Whatever is still
unfilled after bar t+H is cancelled → opportunity cost at Close_{t+H}.

Implementation Shortfall (cost > 0) vs the paper trade Q × arrival:
  timing      Σ q·s·(vwap_k − arrival)     drift between decision and each fill
  spread      Σ q·half_spread_k
  impact      Σ q·impact_k
  commission  Σ commission_k
  opportunity unfilled·s·(Close_{t+H} − arrival)
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import constants as C
from . import cost
from .data import Market

COMPONENTS = ["timing", "spread", "impact", "commission", "opportunity"]


@dataclass(frozen=True)
class Params:
    spread_ticks: float = C.SPREAD_TICKS
    impact_y: float = C.IMPACT_Y
    pov_rate: float = C.POV_RATE
    schedule_cap: float = C.SCHEDULE_CAP
    horizon: int = C.HORIZON_BARS

    def with_(self, **kw) -> "Params":
        return dataclasses.replace(self, **kw)


class Arrays:
    """numpy views of the Market, built once and shared by every run."""

    def __init__(self, mk: Market):
        self.close = mk.close.to_numpy()
        self.value = mk.value.to_numpy()
        self.volume = mk.volume.to_numpy()
        self.vwap = mk.vwap.to_numpy()
        self.hours = mk.hours
        self.index = mk.close.index
        self.col = {t: j for j, t in enumerate(mk.tickers)}
        self.profile = mk.profile.to_dict()


def _vwap_cum_weights(ar: Arrays, t: int, h: int) -> np.ndarray:
    w = np.array([ar.profile.get(int(hr), 0.0) for hr in ar.hours[t + 1: t + 1 + h]])
    if w.sum() <= 0:
        w = np.ones(h)
    return np.cumsum(w) / w.sum()


def execute(order, algo: str, ar: Arrays, p: Params, keep_fills: bool = False) -> tuple[dict, list[dict]]:
    t, j = int(order.decision_i), ar.col[order.ticker]
    s, Q, A, sig = int(order.side), int(order.qty), float(order.arrival_price), float(order.sigma)
    H = p.horizon
    cumw = _vwap_cum_weights(ar, t, H) if algo == "VWAP" else None

    filled = 0
    comp = dict.fromkeys(COMPONENTS, 0.0)
    exec_value = 0.0
    n_child, last_k, max_part = 0, None, 0.0
    fills = []
    for k in range(H):
        rem = Q - filled
        if rem <= 0:
            break
        i = t + 1 + k
        val, px = ar.value[i, j], ar.vwap[i, j]
        if not (val > 0 and np.isfinite(px)):
            continue
        if algo == "MARKET":
            q = rem
        elif algo == "TWAP" or algo == "VWAP":
            frac = (k + 1) / H if algo == "TWAP" else cumw[k]
            target = Q if k == H - 1 else cost.floor_lot(Q * frac)
            q = min(max(target - filled, 0), rem, cost.floor_lot(p.schedule_cap * val / px))
        elif algo == "POV":
            q = min(cost.floor_lot(p.pov_rate * val / px), rem)
        else:
            raise ValueError(f"unknown algo {algo}")
        if q <= 0:
            continue
        c = cost.fill(px, s, q, sig, val, p.spread_ticks, p.impact_y)
        filled += q
        exec_value += c["exec_price"] * q
        comp["timing"] += q * s * (px - A)
        comp["spread"] += q * c["half_spread"]
        comp["impact"] += q * c["impact"]
        comp["commission"] += c["commission"]
        part = q * px / val
        max_part = max(max_part, part)
        n_child, last_k = n_child + 1, k
        if keep_fills:
            fills.append({"order_id": order.order_id, "algo": algo, "bar": i, "datetime": ar.index[i],
                          "slice_k": k + 1, "qty": q, "bar_vwap": px, "bar_value": val,
                          "participation": part, **{f: c[f] for f in ("half_spread", "impact",
                                                                       "exec_price", "commission")}})

    end_i = t + H
    unfilled = Q - filled
    close_end = float(ar.close[end_i, j])
    comp["opportunity"] = unfilled * s * (close_end - A)

    win = slice(t + 1, t + H + 1)
    vol = ar.volume[win, j].sum()
    ivwap = ar.value[win, j].sum() / vol if vol > 0 else np.nan
    avg_exec = exec_value / filled if filled else np.nan
    paper = Q * A
    is_thb = sum(comp.values())
    res = {
        "order_id": order.order_id, "algo": algo, "filled": filled, "fill_rate": filled / Q,
        "n_children": n_child, "bars_used": (last_k + 1) if last_k is not None else np.nan,
        "max_participation": max_part, "avg_exec_price": avg_exec, "interval_vwap": ivwap,
        "vs_ivwap_bps": s * (avg_exec - ivwap) / ivwap * 1e4 if filled and np.isfinite(ivwap) else np.nan,
        "close_end": close_end, "is_thb": is_thb, "is_bps": is_thb / paper * 1e4,
        **{f"{k}_bps": v / paper * 1e4 for k, v in comp.items()},
    }
    return res, fills


def run(orders: pd.DataFrame, ar: Arrays, p: Params = Params(), algos: list[str] = C.ALGOS,
        keep_fills: bool = False) -> tuple[pd.DataFrame, pd.DataFrame]:
    """All orders × all algos → (one row per order×algo merged with the order, fills)."""
    res, fills = [], []
    for o in orders.itertuples(index=False):
        for a in algos:
            r, f = execute(o, a, ar, p, keep_fills)
            res.append(r)
            fills.extend(f)
    out = orders.merge(pd.DataFrame(res), on="order_id")
    return out, pd.DataFrame(fills)
