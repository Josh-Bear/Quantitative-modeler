"""
Module 7: Backtest Engine (bl_spec/07_BACKTEST_ENGINE.md)

Runs the full pipeline (M3 → M6) at every quarterly rebalance date from
BACKTEST_START to the present, holds each portfolio for ~3 months, charges
transaction costs on turnover, and records the realised return series for M8.

Two time periods (07 §2): data before BACKTEST_START is used ONLY to provide
rolling 10-year training windows / estimate Σ for the earliest rebalances — it
is never counted as performance. The rebalance schedule itself starts at
BACKTEST_START, so every realised period recorded here is in the performance
window.

Cost control (07 §5): per-date Module-3 predictions are cached to
output/predictions/{date}.parquet and reused; per-stock training fans out across
CPU workers via predict_universe(n_jobs=...).
"""
from __future__ import annotations

import json
import os
import warnings
from datetime import date
from typing import Optional

import numpy as np
import pandas as pd

from . import constants as C
from . import data_pipeline as dp
from . import selection as sel
from . import black_litterman as bl
from . import optimization as opt
from . import ml_model as ml


# ─────────────────────────────────────────────────────────────────────────────
# Risk-free rate — FRED 3-month T-bill via the public CSV (no API key), 09 §10
# ─────────────────────────────────────────────────────────────────────────────
def get_risk_free_rate() -> float:
    """Latest 3-month T-bill (DTB3) as an annualised decimal, or the fallback.
    Uses FRED's public CSV endpoint (same source as apple_dcf) — no key needed."""
    try:
        import requests
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={C.RISK_FREE_FRED_SERIES}"
        df = pd.read_csv(url)
        col = df.columns[-1]
        vals = pd.to_numeric(df[col], errors="coerce").dropna()
        if len(vals):
            return float(vals.iloc[-1]) / 100.0
    except Exception as e:  # noqa: BLE001
        warnings.warn(f"[M7] risk-free fetch failed ({e}); using "
                      f"{C.RISK_FREE_FALLBACK:.0%} fallback (09 §10).")
    return C.RISK_FREE_FALLBACK


# ─────────────────────────────────────────────────────────────────────────────
# Rebalance schedule  (07 §3)
# ─────────────────────────────────────────────────────────────────────────────
def trading_calendar(tickers: list[str]) -> pd.DatetimeIndex:
    """Union of available trading days across the universe (snap target)."""
    days = pd.DatetimeIndex([])
    for t in tickers[:30]:  # a handful of liquid names defines the calendar
        s = dp.load_close_series(t)
        if s is not None:
            days = days.union(s.index)
    return days.sort_values()


def snap_to_next_trading_day(d: pd.Timestamp, calendar: pd.DatetimeIndex) -> Optional[pd.Timestamp]:
    future = calendar[calendar >= d]
    return future[0] if len(future) else None


def generate_rebalance_dates(backtest_start, backtest_end,
                             calendar: pd.DatetimeIndex) -> list[pd.Timestamp]:
    """Quarterly rebalances snapped to actual trading days (07 §3)."""
    raw = pd.date_range(backtest_start, backtest_end, freq=C.REBALANCE_FREQ)
    out = []
    for d in raw:
        snap = snap_to_next_trading_day(d, calendar)
        if snap is not None and (not out or snap != out[-1]):
            out.append(snap)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Costs & realised returns  (07 §6, §7)
# ─────────────────────────────────────────────────────────────────────────────
def compute_transaction_cost(old_holdings: dict, new_holdings: dict,
                             cost_rate: float = C.TRANSACTION_COST) -> float:
    """Cost on full turnover — every weight change, incl. enters/exits (07 §6, 09 §7)."""
    tickers = set(old_holdings) | set(new_holdings)
    turnover = sum(abs(new_holdings.get(t, 0.0) - old_holdings.get(t, 0.0)) for t in tickers)
    return turnover * cost_rate


def compute_realized_return(holdings: dict, start_date, end_date) -> float:
    """Buy-and-hold portfolio return over [start, end) holding fixed weights
    (weights drift with prices, no intra-period rebalance) (07 §7)."""
    start_ts, end_ts = pd.Timestamp(start_date), pd.Timestamp(end_date)
    total = 0.0
    for ticker, weight in holdings.items():
        s = dp.load_close_series(ticker)
        if s is None:
            continue
        p0, p1 = s.asof(start_ts), s.asof(end_ts)
        if p0 and p1 and p0 > 0 and not (np.isnan(p0) or np.isnan(p1)):
            total += weight * (p1 / p0 - 1.0)
    return total


# ─────────────────────────────────────────────────────────────────────────────
# Per-date Module-3 predictions, with disk cache  (07 §5)
# ─────────────────────────────────────────────────────────────────────────────
def predictions_for_date(tickers: list[str], reb_date, epochs: int,
                         svr_C: float, svr_eps: float, n_jobs: int,
                         force: bool = False) -> pd.DataFrame:
    key = pd.Timestamp(reb_date).date().isoformat()
    path = os.path.join(C.PREDICTIONS_DIR, f"{key}.parquet")
    if os.path.exists(path) and not force:
        return pd.read_parquet(path)
    preds = ml.predict_universe(tickers, reb_date, epochs=epochs,
                                svr_C=svr_C, svr_eps=svr_eps, n_jobs=n_jobs)
    preds.to_parquet(path, index=False)
    return preds


# ─────────────────────────────────────────────────────────────────────────────
# The walk-forward loop  (07 §4)
# ─────────────────────────────────────────────────────────────────────────────
def run_backtest(tickers: list[str], sector_map: dict, epochs: int,
                 svr_C: float, svr_eps: float, n_jobs: int = 1,
                 max_rebalances: Optional[int] = None,
                 rf_annual: Optional[float] = None) -> pd.DataFrame:
    """Run the quarterly walk-forward backtest. Returns the realised-return frame
    (07 §8) and writes the full per-date diagnostic state to backtest_results/."""
    C.ensure_dirs()
    rf_annual = rf_annual if rf_annual is not None else get_risk_free_rate()

    calendar = trading_calendar(tickers)
    # Full quarterly schedule. A dev profile only ACTS on the first
    # `max_rebalances` of them, but each acted period still ends at the next date
    # in the FULL schedule (so a truncated run holds ~one quarter, not 6 years);
    # only the genuinely-final rebalance of the full schedule holds to BACKTEST_END.
    all_reb = generate_rebalance_dates(C.BACKTEST_START, C.BACKTEST_END, calendar)
    reb_dates = all_reb[:max_rebalances] if max_rebalances else all_reb
    print(f"[M7] acting on {len(reb_dates)}/{len(all_reb)} quarterly rebalance dates "
          f"{reb_dates[0].date()} → {reb_dates[-1].date()}; rf={rf_annual:.2%}")

    portfolio_value = 1.0
    current_holdings: dict = {}
    prev_universe: Optional[set] = None
    realized, universe_hist, weights_hist, turnover_log = [], [], [], []

    for i, reb in enumerate(reb_dates):
        print(f"[M7] rebalance {i + 1}/{len(reb_dates)} @ {reb.date()} …")

        # ---- M3: predictions for all stocks (cached) ----
        preds = predictions_for_date(tickers, reb, epochs, svr_C, svr_eps, n_jobs)
        if preds.empty:
            warnings.warn(f"[M7] no predictions at {reb.date()} — skipping date.")
            continue

        # ---- M4: select the 22-stock universe ----
        universe = sel.select_universe(preds, sector_map)
        universe.to_parquet(os.path.join(C.UNIVERSE_DIR, f"{reb.date()}.parquet"), index=False)
        new_set = set(universe["ticker"])

        # ---- M5: Black-Litterman posterior ----
        bl_out = bl.compute_bl_pipeline(universe, reb)
        if bl_out is None:
            warnings.warn(f"[M7] BL failed at {reb.date()} — skipping date.")
            continue
        _save_bl(bl_out, reb)

        # ---- M6: max-Sharpe weights ----
        port = opt.optimize(bl_out["mu_BL"], bl_out["Sigma"], bl_out["stock_order"],
                            rf_annual=rf_annual)
        new_holdings = dict(zip(bl_out["stock_order"], port["w_star"]))
        _save_portfolio(port, reb)

        # ---- transaction cost on turnover ----
        cost = compute_transaction_cost(current_holdings, new_holdings)
        portfolio_value *= (1 - cost)

        # ---- hold to the next rebalance in the FULL schedule (or backtest end) ----
        next_reb = all_reb[i + 1] if i + 1 < len(all_reb) else pd.Timestamp(C.BACKTEST_END)
        period_return = compute_realized_return(new_holdings, reb, next_reb)
        portfolio_value *= (1 + period_return)

        realized.append({"date": reb, "period_end": next_reb,
                         "period_return": period_return,
                         "transaction_cost": cost, "portfolio_value": portfolio_value})
        turn = sel.compute_universe_turnover(prev_universe, new_set)
        turnover_log.append({"date": reb, "overlap_pct": turn["overlap_pct"],
                             "n_entered": len(turn["entered"]), "n_exited": len(turn["exited"]),
                             "entered": " ".join(sorted(turn["entered"])),
                             "exited": " ".join(sorted(turn["exited"]))})
        for t, w in new_holdings.items():
            weights_hist.append({"date": reb, "ticker": t, "weight": w})
        universe_hist.append({"date": reb, "tickers": " ".join(bl_out["stock_order"])})

        current_holdings = new_holdings
        prev_universe = new_set

    results = pd.DataFrame(realized)
    _save_outputs(results, universe_hist, weights_hist, turnover_log)
    return results


# ─────────────────────────────────────────────────────────────────────────────
# Persistence (07 §8 output contract)
# ─────────────────────────────────────────────────────────────────────────────
def _save_bl(bl_out: dict, reb) -> None:
    key = pd.Timestamp(reb).date().isoformat()
    np.savez(os.path.join(C.BL_DIR, f"{key}.npz"),
             mu_BL=bl_out["mu_BL"], Sigma=bl_out["Sigma"], Pi=bl_out["Pi"],
             P=bl_out["P"], Q=bl_out["Q"], Omega=bl_out["Omega"], w_mkt=bl_out["w_mkt"])
    meta = {"rebalance_date": key, "stock_order": bl_out["stock_order"],
            "n_absolute_views": bl_out["n_absolute_views"],
            "n_relative_views": bl_out["n_relative_views"]}
    with open(os.path.join(C.BL_DIR, f"{key}.json"), "w") as fh:
        json.dump(meta, fh, indent=2)


def _save_portfolio(port: dict, reb) -> None:
    key = pd.Timestamp(reb).date().isoformat()
    np.savez(os.path.join(C.PORTFOLIO_DIR, f"{key}.npz"),
             w_star=port["w_star"], sharpe=port["w_star_sharpe"],
             stock_order=np.array(port["stock_order"], dtype=object))
    if not port["frontier"].empty:
        fr = port["frontier"][["target_return", "volatility"]].copy()
        fr.to_parquet(os.path.join(C.PORTFOLIO_DIR, f"{key}_frontier.parquet"), index=False)


def _save_outputs(results, universe_hist, weights_hist, turnover_log) -> None:
    results.to_parquet(os.path.join(C.BACKTEST_DIR, "realized_returns.parquet"), index=False)
    pd.DataFrame(universe_hist).to_parquet(
        os.path.join(C.BACKTEST_DIR, "universe_history.parquet"), index=False)
    pd.DataFrame(weights_hist).to_parquet(
        os.path.join(C.BACKTEST_DIR, "weights_history.parquet"), index=False)
    pd.DataFrame(turnover_log).to_csv(
        os.path.join(C.BACKTEST_DIR, "turnover_log.csv"), index=False)
