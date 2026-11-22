"""
metrics.py — execution quality per order / per strategy, and portfolio results.

Implementation Shortfall (cost > 0), relative to the paper trade Q × arrival:
  IS = timing + spread + impact + commission + opportunity
    timing      Σ q·s·(mid_k − arrival)        price drift while working the order
    spread      Σ q·half_spread_k
    impact      Σ q·impact_k
    commission  Σ commission_k
    opportunity cancelled·s·(cancel_price − arrival)

Benchmarks over the execution window, bars t+1 … t+BENCH_BARS after the
decision bar t (the same window for every strategy, so they are comparable):
  twap_benchmark   mean Close
  vwap_benchmark   Σ TRADING_VALUE / Σ TRADING_VOLUME  (market VWAP)
  vs_*_bps         side × (avg fill − benchmark) / benchmark  (> 0 = worse than benchmark)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import constants as C
from .data_loader import MarketData, bars_per_day

COMPONENTS = ["timing", "spread", "impact", "commission", "opportunity"]


def _benchmarks(md: MarketData, ticker: str, arrival_i: int) -> tuple[float, float]:
    lo, hi = arrival_i + 1, arrival_i + 1 + C.BENCH_BARS
    close = md.close[ticker].to_numpy()[lo:hi]
    if not len(close):
        return np.nan, np.nan
    vol = md.volume[ticker].to_numpy()[lo:hi].sum()
    vwap = md.value[ticker].to_numpy()[lo:hi].sum() / vol if vol > 0 else np.nan
    return float(close.mean()), float(vwap)


def _vs(side: int, avg_fill: float, bench: float) -> float:
    return side * (avg_fill - bench) / bench * 1e4 if np.isfinite(avg_fill) and np.isfinite(bench) else np.nan


def order_table(result: dict, md: MarketData) -> pd.DataFrame:
    fills = pd.DataFrame(result["fills"])
    rows = []
    for o in result["orders"]:
        f = fills[fills["order_id"] == o.order_id] if len(fills) else fills
        s, A, Q = o.side, o.arrival_price, o.qty
        paper = Q * A
        F = int(f["qty"].sum()) if len(f) else 0
        comp = {
            "timing": float((f["qty"] * s * (f["mid"] - A)).sum()) if F else 0.0,
            "spread": float((f["qty"] * f["half_spread"]).sum()) if F else 0.0,
            "impact": float((f["qty"] * f["impact"]).sum()) if F else 0.0,
            "commission": float(f["commission"].sum()) if F else 0.0,
            "opportunity": (o.cancelled * s * (o.cancel_price - A)) if o.cancelled else 0.0,
        }
        is_thb = sum(comp.values())
        avg_fill = float((f["qty"] * f["exec_price"]).sum() / F) if F else np.nan
        twap, vwap = _benchmarks(md, o.ticker, o.arrival_i)
        rows.append({
            "order_id": o.order_id, "strategy": o.strategy, "ticker": o.ticker,
            "side": "BUY" if s > 0 else "SELL", "reason": o.reason,
            "arrival_time": o.arrival_dt, "arrival_price": A,
            "current_w": o.current_w, "target_w": o.target_w,
            "qty": Q, "filled": F, "cancelled": o.cancelled, "fill_rate": F / Q,
            "avg_fill_price": avg_fill, "twap_benchmark": twap, "vwap_benchmark": vwap,
            "vs_twap_bps": _vs(s, avg_fill, twap), "vs_vwap_bps": _vs(s, avg_fill, vwap),
            "n_fills": len(f), "bars_to_complete": (o.last_fill_i - o.arrival_i) if F else np.nan,   # bars after the decision bar
            "paper_notional": paper, "is_thb": is_thb, "is_bps": is_thb / paper * 1e4,
            **{f"{k}_thb": v for k, v in comp.items()},
            **{f"{k}_bps": v / paper * 1e4 for k, v in comp.items()},
            "cancel_reason": o.cancel_reason,
        })
    return pd.DataFrame(rows)


def portfolio_stats(nav: pd.Series, traded_notional: float) -> dict:
    ret = nav.pct_change().dropna()
    bpy = bars_per_day(nav.index) * C.TRADING_DAYS_PER_YEAR
    dd = nav / nav.cummax() - 1.0
    sd = ret.std()
    return {
        "start_nav": float(nav.iloc[0]), "final_nav": float(nav.iloc[-1]),
        "total_return": float(nav.iloc[-1] / nav.iloc[0] - 1.0),
        "ann_vol": float(sd * np.sqrt(bpy)),
        "sharpe": float(ret.mean() / sd * np.sqrt(bpy)) if sd > 0 else np.nan,
        "max_drawdown": float(dd.min()),
        "turnover": float(traded_notional / nav.mean()),
    }


def strategy_summary(orders: pd.DataFrame, result: dict) -> dict:
    log = pd.DataFrame(result["pretrade_log"])
    fills = pd.DataFrame(result["fills"])
    traded = float(fills["notional"].sum()) if len(fills) else 0.0
    paper = orders["paper_notional"].sum() if len(orders) else 0.0
    out = {
        "strategy": result["strategy"], "n_slices": result["n_slices"],
        "n_orders": len(orders),
        "n_buy": int((orders["side"] == "BUY").sum()) if len(orders) else 0,
        "n_sell": int((orders["side"] == "SELL").sum()) if len(orders) else 0,
        "pretrade_rejects": int((log["action"] == "REJECT").sum()) if len(log) else 0,
        "pretrade_adjusts": int((log["action"] == "ADJUST").sum()) if len(log) else 0,
        "traded_notional": traded,
    }
    if len(orders):
        out.update({
            "fill_rate_avg": float(orders["fill_rate"].mean()),
            "fill_rate_value_wtd": float((orders["filled"] * orders["arrival_price"]).sum() / paper),
            "is_bps_mean": float(orders["is_bps"].mean()),
            "is_bps_median": float(orders["is_bps"].median()),
            "is_bps_std": float(orders["is_bps"].std()),
            "is_bps_value_wtd": float(orders["is_thb"].sum() / paper * 1e4),
            **{f"{k}_bps_value_wtd": float(orders[f"{k}_thb"].sum() / paper * 1e4) for k in COMPONENTS},
            "total_cost_thb": float(orders["is_thb"].sum()),
            "vs_twap_bps_mean": float(orders["vs_twap_bps"].mean()),
            "vs_vwap_bps_mean": float(orders["vs_vwap_bps"].mean()),
            "bars_to_complete_avg": float(orders["bars_to_complete"].mean()),
        })
    out.update(portfolio_stats(result["nav"]["nav"], traded))
    return out


def comparison(results: dict[str, dict], md: MarketData) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (all orders, comparison table with one column per strategy)."""
    tables, summaries = [], {}
    for name, res in results.items():
        o = order_table(res, md)
        tables.append(o)
        summaries[name] = strategy_summary(o, res)
    return pd.concat(tables, ignore_index=True), pd.DataFrame(summaries)
