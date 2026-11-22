"""
test.py — network-free sanity checks for the order_execution simulator.

    python test.py
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from src import constants as C
from src import data_loader, metrics, signals, simulator
from src.execution import ParentOrder, execute_bar, split_lots
from src.market_rules import ceil_lot, floor_lot, round_to_tick, tick_size

TOL = 1e-6
_results: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, detail: str = ""):
    _results.append((name, bool(cond), detail))


# ─── market rules ────────────────────────────────────────────────────────────
def test_tick_table():
    cases = {1.99: 0.01, 2.0: 0.02, 4.98: 0.02, 5.0: 0.05, 9.95: 0.05, 10.0: 0.10, 24.9: 0.10,
             25.0: 0.25, 99.75: 0.25, 100.0: 0.50, 199.5: 0.50, 200.0: 1.0, 399.0: 1.0, 400.0: 2.0}
    bad = {p: tick_size(p) for p, t in cases.items() if tick_size(p) != t}
    check("tick size follows SET table", not bad, str(bad))
    check("round_to_tick nearest/up/down",
          round_to_tick(33.13) == 33.25 and round_to_tick(33.13, "down") == 33.0
          and round_to_tick(33.0, "up") == 33.0 and round_to_tick(7.52, "up") == 7.55)


def test_lots():
    check("floor_lot / ceil_lot",
          floor_lot(250) == 200 and floor_lot(-250) == -200 and floor_lot(99) == 0
          and ceil_lot(201) == 300 and ceil_lot(-201) == -300 and ceil_lot(200) == 200)
    check("split_lots sums and is lot-sized",
          split_lots(1_300, 5) == [300, 300, 300, 200, 200] and sum(split_lots(10_000, 5)) == 10_000)


# ─── signals ─────────────────────────────────────────────────────────────────
def test_signals_fire_once():
    n_flat, n_ramp = 60, 40
    flat = 100 + 0.3 * np.sin(np.arange(n_flat))
    ramp = flat[-1] * 1.01 ** np.arange(1, n_ramp + 1)        # RSI pinned > 80 for many bars
    close = pd.Series(np.r_[flat, ramp], index=pd.RangeIndex(n_flat + n_ramp))
    s = signals.compute_signals(close)
    during = s.iloc[n_flat:]
    above80 = int((during["rsi"] > C.RSI_SELL).sum())
    sells = int((during["signal_code"] == signals.SELL).sum())
    check("RSI > 80 for many bars → exactly one SELL", above80 > 5 and sells == 1,
          f"bars RSI>80={above80}, sells={sells}")


def test_one_buy_per_cross():
    prices = data_loader.synthetic_prices().close
    worst = 0
    for t in prices.columns:
        s = signals.compute_signals(prices[t])
        above = (s["sma_fast"] > s["sma_slow"]).astype(int)
        regime = (above.diff() == 1).cumsum()                 # id of each cross-up episode
        buys = s[s["signal_code"] == signals.BUY].groupby(regime).size()
        worst = max(worst, int(buys.max()) if len(buys) else 0)
    check("at most one BUY per cross-up", worst <= 1, f"max BUYs in one episode = {worst}")


# ─── full simulation invariants ──────────────────────────────────────────────
def test_simulation_invariants():
    md = data_loader.synthetic_prices()
    prices = md.close
    sig = signals.compute_all(prices)
    results = simulator.run_all(md, sig)
    for name, res in results.items():
        nav, fills = res["nav"], pd.DataFrame(res["fills"])
        sh = nav[[f"sh_{t}" for t in prices.columns]]
        check(f"[{name}] cash never negative",
              nav["cash"].min() >= -TOL and fills["cash_after"].min() >= -TOL,
              f"min cash {min(nav['cash'].min(), fills['cash_after'].min()):,.2f}")
        check(f"[{name}] no short positions", (sh.to_numpy() >= 0).all())
        check(f"[{name}] every fill is board-lot sized", (fills["qty"] % C.LOT == 0).all())
        first_fill = fills.groupby("order_id")["bar"].min()
        arrival = {o.order_id: o.arrival_i for o in res["orders"]}
        check(f"[{name}] no fill in the decision bar (first fill ≥ arrival + 1)",
              all(b > arrival[k] for k, b in first_fill.items()))
        check(f"[{name}] child ≤ participation cap × bar value",
              (fills["participation"] <= C.PARTICIPATION_CAP + 1e-9).all(),
              f"max {fills['participation'].max():.4f}")
        check(f"[{name}] filled + cancelled = parent qty",
              all(o.filled + o.cancelled == o.qty and o.status == "DONE" for o in res["orders"]))
        recomputed = nav["cash"] + (sh.to_numpy() * prices.to_numpy()).sum(axis=1)
        check(f"[{name}] NAV = cash + Σ shares × close", np.allclose(recomputed, nav["nav"], atol=1e-4))
        log = pd.DataFrame(res["pretrade_log"])
        warns = int((log["check"] == "POST_TRADE").sum()) if len(log) else 0
        check(f"[{name}] no post-trade weight breaches", warns == 0, f"{warns} warnings")
        # weight right after a completed market order sits inside the bounds
        if res["n_slices"] == 1:
            bad = 0
            for o in res["orders"]:
                if o.filled == o.qty:
                    w = nav.iloc[o.last_fill_i][f"w_{o.ticker}"]
                    bad += not (C.W_MIN - 1e-3 <= w <= C.W_MAX + 1e-3)
            check(f"[{name}] post-trade weight in [{C.W_MIN:.0%}, {C.W_MAX:.0%}]", bad == 0, f"{bad} orders")
        # orders are rare events — not one per bar
        check(f"[{name}] orders are events, not every bar", len(res["orders"]) < 0.1 * len(prices) * len(prices.columns))


# ─── cost model / metrics on controlled prices ───────────────────────────────
BAR_VALUE = 200_000_000.0            # THB traded per bar in the controlled tests → cap 20 M


def _md(close, value) -> data_loader.MarketData:
    idx = pd.RangeIndex(len(close))
    c = pd.DataFrame({"X": np.asarray(close, float)}, index=idx)
    v = pd.DataFrame({"X": np.asarray(value, float)}, index=idx)
    return data_loader.MarketData(c, v, v / c, {})


def _run_single(qty: int, n_slices: int, price: float | list = 50.0, sigma: float = 0.0, bars: int = 10,
                value: float | list = BAR_VALUE, side: int = 1):
    if not np.isscalar(price):
        bars = len(price)
    elif not np.isscalar(value):
        bars = len(value)
    close = np.full(bars, price, dtype=float) if np.isscalar(price) else np.asarray(price, float)
    val = np.full(bars, value, dtype=float) if np.isscalar(value) else np.asarray(value, float)
    md = _md(close, val)
    o = ParentOrder(1, f"S{n_slices}", "X", side, qty, "TEST", 0, 0, close[0], 0.1, 0.1, n_slices)
    fills, cash = [], 1e12
    for i in range(bars):
        f = execute_bar(o, i, i, close[i], sigma, cash, val[i])
        if f:
            fills.append(f)
            cash += f["cash_flow"]
        if o.status != "OPEN":
            break
    res = {"orders": [o], "fills": fills}
    return metrics.order_table(res, md).iloc[0], o


def test_static_price_is_spread_plus_commission():
    for n in (1, 5):
        r, _ = _run_single(10_000, n)
        expect_spread_bps = tick_size(50.0) / 2 / 50.0 * 1e4
        expect_comm_bps = C.COMMISSION_ALL_IN * (1 + expect_spread_bps / 1e4) * 1e4
        ok = (abs(r["timing_bps"]) < TOL and abs(r["impact_bps"]) < TOL
              and abs(r["spread_bps"] - expect_spread_bps) < 1e-6
              and abs(r["commission_bps"] - expect_comm_bps) < 1e-6
              and abs(r["is_bps"] - (r["spread_bps"] + r["commission_bps"])) < 1e-9)
        check(f"σ=0, flat price → IS = spread + commission (slices={n})", ok,
              f"IS {r['is_bps']:.4f} = spread {r['spread_bps']:.4f} + comm {r['commission_bps']:.4f}")


def test_large_order_market_costs_more_than_twap():
    qty = 300_000                     # 15 M THB, under the 20 M per-bar cap
    (m, _), (t, _) = _run_single(qty, 1, sigma=0.005), _run_single(qty, 5, sigma=0.005)
    check("large order: MARKET impact > TWAP impact", m["impact_bps"] > t["impact_bps"] > 0,
          f"MARKET {m['impact_bps']:.2f} bps vs TWAP {t['impact_bps']:.2f} bps")
    check("large order: MARKET IS > TWAP IS (flat price)", m["is_bps"] > t["is_bps"],
          f"MARKET {m['is_bps']:.2f} vs TWAP {t['is_bps']:.2f}")


def test_participation_cap_limits_market():
    qty = 2_000_000                   # 100 M THB vs 20 M per-bar cap
    (m, _), (t, _) = _run_single(qty, 1), _run_single(qty, 5)
    check("participation cap → MARKET partially filled, TWAP fills more",
          m["fill_rate"] < 1.0 and t["fill_rate"] > m["fill_rate"],
          f"fill rate MARKET {m['fill_rate']:.0%}, TWAP {t['fill_rate']:.0%}")


def test_next_bar_fill_timing():
    # decide at Close_0 = 50, MARKET fills at Close_1 = 51 → buy pays +200 bps timing
    r, o = _run_single(10_000, 1, price=[50.0, 51.0, 51.0])
    check("MARKET fills in the bar after the decision", o.last_fill_i == 1 and r["fill_rate"] == 1.0,
          f"fill bar {o.last_fill_i}")
    check("timing = Close_{t+1} − arrival (MARKET)", abs(r["timing_bps"] - 200.0) < 1e-9,
          f"timing {r['timing_bps']:.4f} bps")
    r, _ = _run_single(10_000, 1, price=[50.0, 49.0, 49.0], side=-1)
    check("sell: price drop before the fill is a timing cost", abs(r["timing_bps"] - 200.0) < 1e-9,
          f"timing {r['timing_bps']:.4f} bps")


def test_zero_value_bar_does_not_fill():
    r, o = _run_single(10_000, 1, value=[BAR_VALUE, 0.0, BAR_VALUE])
    check("MARKET: no trading in t+1 → nothing filled, cancelled", r["fill_rate"] == 0.0 and o.cancelled == 10_000)
    r, o = _run_single(10_000, 5, value=[BAR_VALUE, 0.0] + [BAR_VALUE] * 8)
    check("TWAP: no-trade bar is carried to the next slice", r["fill_rate"] == 1.0 and r["n_fills"] == 4,
          f"fills {r['n_fills']}, fill rate {r['fill_rate']:.0%}")


def test_vwap_benchmark():
    # flat price, value = price × volume → market VWAP = price; fill pays half spread above it
    r, _ = _run_single(10_000, 5)
    expect = tick_size(50.0) / 2 / 50.0 * 1e4
    check("VWAP benchmark = price on flat data; vs VWAP = half spread",
          abs(r["vwap_benchmark"] - 50.0) < 1e-9 and abs(r["vs_vwap_bps"] - expect) < 1e-6,
          f"vwap {r['vwap_benchmark']:.4f}, vs {r['vs_vwap_bps']:.4f} bps")


def test_loader_long_format():
    rows = [
        # ticker, datetime, close, value, volume
        ("AAA", "2025-01-02 10:00:00", 10.0, 1e6, 1e5), ("BBB", "2025-01-02 10:00:00", 20.0, 2e6, 1e5),
        ("AAA", "2025-01-02 11:00:00", 10.1, 1e6, 1e5),                      # BBB missing → ffill, value 0
        ("BBB", "2025-01-02 11:00:00", None, None, None),
        ("AAA", "2025-01-02 14:00:00", 10.2, 1e6, 1e5), ("BBB", "2025-01-02 14:00:00", 20.2, 2e6, 1e5),  # dropped hour
        ("AAA", "2025-01-03 01:00:00", 10.3, 1e3, 1e2),                      # off-hours → dropped
        ("AAA", "2025-01-03 10:00:00", 10.4, 1e6, 1e5), ("BBB", "2025-01-03 10:00:00", 20.4, 2e6, 1e5),
    ]
    df = pd.DataFrame([r for r in rows if r[2] is not None],
                      columns=["TICKER", "DATE", "CLOSE_PRC", "TRADING_VALUE", "TRADING_VOLUME"])
    df.insert(0, "ID", 1)
    with tempfile.TemporaryDirectory() as d:
        f1, f2 = Path(d) / "a.csv", Path(d) / "b.csv"
        df.iloc[:4].to_csv(f1, index=False)
        df.iloc[4:].to_csv(f2, index=False)
        md = data_loader.load_csv([f1, f2], tickers=["AAA", "BBB"], hours=[10, 11, 12, 13, 15, 16, 17])
    ok = (len(md.close) == 3 and list(md.close.columns) == ["AAA", "BBB"]
          and md.close.loc["2025-01-02 11:00", "BBB"] == 20.0
          and md.value.loc["2025-01-02 11:00", "BBB"] == 0.0
          and md.info["rows_off_grid_dropped"] == 3)
    check("loader: long CSVs merged, off-grid hours dropped, gap ffilled with value 0", ok,
          f"rows {len(md.close)}, dropped {md.info['rows_off_grid_dropped']}")


def test_real_data_if_present():
    files = data_loader.data_files()
    if not files:
        check("real data present (skipped — no SET50_*.csv)", True)
        return
    md = data_loader.load_csv(files)
    check("real data: 7 bars/day, the 10 configured tickers, no NaN",
          data_loader.bars_per_day(md.close.index) == 7 and list(md.close.columns) == C.TICKERS
          and not md.close.isna().any().any() and not md.value.isna().any().any(),
          f"{len(md.close)} bars, {md.info['start']} → {md.info['end']}")


if __name__ == "__main__":
    for fn in [test_tick_table, test_lots, test_signals_fire_once, test_one_buy_per_cross,
               test_simulation_invariants, test_static_price_is_spread_plus_commission,
               test_large_order_market_costs_more_than_twap, test_participation_cap_limits_market,
               test_next_bar_fill_timing, test_zero_value_bar_does_not_fill, test_vwap_benchmark,
               test_loader_long_format, test_real_data_if_present]:
        fn()
    width = max(len(n) for n, _, _ in _results)
    for name, ok, detail in _results:
        print(f"{'PASS' if ok else 'FAIL'}  {name:<{width}}  {detail}")
    failed = sum(not ok for _, ok, _ in _results)
    print(f"\n{len(_results) - failed}/{len(_results)} passed")
    raise SystemExit(1 if failed else 0)
