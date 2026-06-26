"""
run.py — orchestrate the bl_lstm_views pipeline end to end.

    fetch → indicators → preprocess → train LSTM → SVR → views → Black-Litterman → backtest

Usage:
    python run.py                  # default profile (~6 stocks, fast)
    python run.py --quick          # smoke test (2 stocks, 3 epochs)
    python run.py --full           # paper scope (full DJI list, 400 epochs — slow!)
    python run.py --tickers AAPL,MSFT,NVDA
    python run.py --epochs 50

Outputs: output/views.json (BL view package) and output/report.txt (this summary).
"""
from __future__ import annotations

import argparse
import os

import numpy as np
import pandas as pd
import torch

from src import black_litterman as bl
from src import constants as C
from src import fetch_data
from src.backtest import run_backtest
from src.lstm_model import get_device
from src.preprocessing import build_stock_dataset
from src.views import generate_views, write_views_json

_LINES: list[str] = []


def emit(line: str = "") -> None:
    print(line)
    _LINES.append(line)


def parse_args():
    p = argparse.ArgumentParser(description="LSTM+SVR investor's-view generator for Black-Litterman")
    p.add_argument("--quick", action="store_true", help="smoke profile: 2 stocks, 3 epochs")
    p.add_argument("--full", action="store_true", help="paper profile: full DJI list, 400 epochs")
    p.add_argument("--tickers", type=str, default="", help="comma-separated override of the universe")
    p.add_argument("--epochs", type=int, default=0, help="override LSTM epochs")
    p.add_argument("--device", type=str, default="auto", choices=["auto", "cpu", "mps", "cuda"],
                   help="compute device (default auto; use cpu if the GPU is memory-pressured)")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    profile = "quick" if args.quick else "full" if args.full else "default"
    cfg = C.resolve_profile(profile)
    universe = ([t.strip().upper() for t in args.tickers.split(",") if t.strip()]
                if args.tickers else cfg["universe"])
    epochs = args.epochs or cfg["epochs"]
    max_weight = cfg["max_weight"]

    for d in (C.OUTPUT_DIR, C.CACHE_DIR, C.MODELS_DIR):
        os.makedirs(d, exist_ok=True)

    device = get_device(args.device)
    emit("=" * 70)
    emit("  BL · LSTM + SVR  Investor's-View Generator")
    emit(f"  profile={profile}  universe={universe}  epochs={epochs}  device={device.type}")
    emit("=" * 70)

    # ── 1. fetch ─────────────────────────────────────────────────────────────
    emit("\n[1/5] Fetching market data ...")
    data = fetch_data.fetch(universe)
    skipped: dict[str, str] = {}   # accumulate all skipped tickers + reasons
    if data["errors"]:
        for t, why in data["errors"].items():
            emit(f"   ⚠️  {t}: skipped ({why})")
            skipped[t] = why
    bench = fetch_data.download_prices(C.BENCHMARK, C.DATA_START, C.DATA_END)
    bench_close = bench["close"] if bench is not None else None
    if bench_close is None:
        emit(f"   ⚠️  {C.BENCHMARK}: unavailable — backtest will run without a benchmark.")

    # ── 2. build per-stock datasets ──────────────────────────────────────────
    emit("\n[2/5] Computing indicators + windows ...")
    stock_data, caps = {}, {}
    for t, df in data["prices"].items():
        try:
            stock_data[t] = build_stock_dataset(t, df)
            caps[t] = data["market_caps"].get(t, 0.0)
            emit(f"   ✅ {t}: {len(stock_data[t].dates)} usable days, "
                 f"{stock_data[t].windows['X'].shape[0]} windows")
        except Exception as e:
            emit(f"   ⚠️  {t}: skipped ({e})")
            skipped[t] = str(e)
    tickers = list(stock_data.keys())
    if len(tickers) < 2:
        emit("\n✖ Need at least 2 usable tickers — aborting.")
        return 1

    # ── 3. views (train LSTM + SVR) ──────────────────────────────────────────
    emit(f"\n[3/5] Generating views ({len(tickers)} stocks × 8 LSTM + SVR) ...")
    try:
        views = generate_views(stock_data, epochs=epochs, device=device)
    except RuntimeError as e:
        if device.type != "cpu" and "out of memory" in str(e).lower():
            emit(f"   ⚠️  {device.type.upper()} out of memory (the GPU shares system RAM — "
                 "close other apps or use --device cpu).")
            emit("   ↩  Retrying on CPU (slower) ...")
            device = torch.device("cpu")
            views = generate_views(stock_data, epochs=epochs, device=device)
        else:
            raise

    # reconcile the universe to whatever actually produced a view — any stock that
    # failed to train was skipped inside generate_views, so drop it everywhere.
    dropped = [t for t in tickers if t not in views["tickers"]]
    if dropped:
        emit(f"   ⚠️  no views for {dropped} — continuing without them.")
    tickers = list(views["tickers"])
    stock_data = {t: stock_data[t] for t in tickers}
    caps = {t: caps[t] for t in tickers}
    if len(tickers) < 2:
        emit("\n✖ Fewer than 2 stocks produced usable views — aborting.")
        return 1

    # ── 4. Black-Litterman (current allocation) ──────────────────────────────
    emit("\n[4/5] Black-Litterman allocation ...")
    panel = pd.DataFrame({t: pd.Series(stock_data[t].close_raw,
                          index=pd.DatetimeIndex(stock_data[t].dates).normalize())
                          for t in tickers}).dropna()
    sigma = bl.covariance(panel.pct_change().dropna().to_numpy())
    w_mkt = bl.market_weights(np.array([caps[t] for t in tickers]))
    res = bl.solve(sigma, w_mkt, P=views["P"], Q=views["Q"], omega=views["omega"],
                   max_weight=max_weight)

    emit("\n  Weights & returns (annualised):")
    emit(f"  {'Ticker':<8}{'w_mkt':>9}{'w*':>9}{'Δw':>9}{'Π':>9}{'μ_BL':>9}{'Q(view)':>10}")
    emit("  " + "-" * 62)
    for i, t in enumerate(tickers):
        emit(f"  {t:<8}{w_mkt[i]:>8.1%}{res['w_star'][i]:>9.1%}"
             f"{res['w_star'][i]-w_mkt[i]:>+9.1%}"
             f"{res['pi'][i]:>9.1%}{res['mu_bl'][i]:>9.1%}{views['Q'][i]:>10.1%}")
    emit(f"\n  Portfolio (w*):  E[R]={bl.portfolio_return(res['w_star'], res['mu_bl']):.1%}"
         f"  vol={bl.portfolio_vol(res['w_star'], sigma):.1%}"
         f"  Sharpe={bl.sharpe(res['w_star'], res['mu_bl'], sigma):.2f}"
         f"  TE={bl.tracking_error(res['w_star'], w_mkt, sigma):.1%}")
    emit(f"  Unconstrained leverage Σ|wᵢ|: {res['leverage']:.2f}×")

    # ── 5. backtest ──────────────────────────────────────────────────────────
    emit("\n[5/5] Backtest vs SPY (rolling 5-day rebalance, test window) ...")
    bt = run_backtest(stock_data, views, w_mkt, bench_close, max_weight=max_weight)
    if bt.get("ok"):
        s, b = bt["strategy"], bt["benchmark"]
        emit(f"  grid {bt['grid_start']} → {bt['grid_end']}  ({bt['n_rebalances']} rebalances)")
        emit(f"  {'':<14}{'Ann.Return':>12}{'Ann.Vol':>10}{'Sharpe':>9}{'MaxDD':>9}")
        emit("  " + "-" * 52)
        emit(f"  {'BL+model':<14}{s['ann_return']:>12.1%}{s['ann_vol']:>10.1%}"
             f"{s['sharpe']:>9.2f}{s['max_drawdown']:>9.1%}")
        if b:
            emit(f"  {'SPY buy&hold':<14}{b['ann_return']:>12.1%}{b['ann_vol']:>10.1%}"
                 f"{b['sharpe']:>9.2f}{b['max_drawdown']:>9.1%}")
    else:
        emit(f"  (skipped: {bt.get('reason')})")

    # ── diagnostics ──────────────────────────────────────────────────────────
    emit("\n  Model diagnostics:")
    emit(f"  {'Ticker':<8}{'last_close':>12}{'pred_5d':>10}{'q_5d':>8}"
         f"{'LSTM_MSE':>10}{'SVR_MSE':>10}")
    emit("  " + "-" * 58)
    for t in tickers:
        d = views["per_stock"][t]
        emit(f"  {t:<8}{d['last_close']:>12.2f}{d['pred_price']:>10.2f}"
             f"{d['q_horizon']:>8.1%}{d['lstm_mse_mean']:>10.4f}{d['svr_fit_mse']:>10.4f}")

    # ── QA checklist ─────────────────────────────────────────────────────────
    emit("\n  QA checklist:")
    w = res["w_star"]
    # the cap auto-relaxes to 1/n when max_weight is infeasible for a small universe
    eff_cap = max(max_weight, 1.0 / len(tickers))
    checks = [
        ("weights sum to 1.0", abs(w.sum() - 1.0) < 1e-6),
        (f"weights within [0, {eff_cap:.0%}] (effective cap)",
         bool(np.all(w >= -1e-9) and np.all(w <= eff_cap + 1e-6))),
        ("Q finite", bool(np.all(np.isfinite(views["Q"])))),
        ("Ω strictly positive", bool(np.all(views["omega"] > 0))),
        ("Σ symmetric", bool(np.allclose(sigma, sigma.T, atol=1e-8))),
    ]
    for name, ok in checks:
        emit(f"    {'✅' if ok else '❌'} {name}")

    # ── skipped tickers summary ───────────────────────────────────────────────
    if skipped:
        emit("\n  ⚠️  Skipped tickers (excluded from model):")
        emit(f"  {'Ticker':<8}  Reason")
        emit("  " + "-" * 62)
        for t, reason in sorted(skipped.items()):
            emit(f"  {t:<8}  {reason}")
        emit(f"\n  → {len(skipped)} ticker(s) skipped, {len(tickers)} used in the model.")
    else:
        emit(f"\n  → All {len(tickers)} tickers used in the model (none skipped).")

    # ── persist ──────────────────────────────────────────────────────────────
    write_views_json(views)
    with open(C.REPORT_TXT, "w") as f:
        f.write("\n".join(_LINES) + "\n")
    emit(f"\n  → views written to {os.path.relpath(C.VIEWS_JSON, C.ROOT_DIR)}")
    emit(f"  → report written to {os.path.relpath(C.REPORT_TXT, C.ROOT_DIR)}")
    emit("\n  Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
