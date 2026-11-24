"""
test.py — network-free checks for the execution-algorithm research.

    python test.py

Controlled markets are built in memory (no data needed); the last block runs
invariants on the real SET50 files when they are present.
"""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd

from src import constants as C
from src import cost, data, orders, stats
from src.engine import Arrays, Params, execute, run

_results: list[tuple[str, bool, str]] = []
H = C.HORIZON_BARS
NH = len(C.SESSION_HOURS)                  # bars per day
DAYS = 40                                  # > PROFILE_DAYS so the rolling profile exists
T0 = 26 * NH + 2                           # decision bar used in the controlled tests (day 27, 12:00)


def check(name: str, cond, detail: str = ""):
    _results.append((name, bool(cond), detail))


# ─── helpers ──────────────────────────────────────────────────────────────────
def _bars(days: int, close, value, tickers=("X",), start="2024-01-02") -> pd.DataFrame:
    """Long bars on the SESSION_HOURS grid. close/value: scalar, or array of length days × NH."""
    dates = pd.bdate_range(start, periods=days)
    dts = [d + pd.Timedelta(hours=h) for d in dates for h in C.SESSION_HOURS]
    n = len(dts)
    rows = []
    for tk in tickers:
        c = np.full(n, close, float) if np.isscalar(close) else np.asarray(close, float)
        v = np.full(n, value, float) if np.isscalar(value) else np.asarray(value, float)
        rows.append(pd.DataFrame({"ticker": tk, "dt": dts, "close": c, "low": c, "high": c,
                                  "value": v, "volume": np.where(v > 0, v / c, 0.0)}))
    return pd.concat(rows, ignore_index=True)


def _market(days=DAYS, close=50.0, value=200e6, **kw):
    mk = data.build_market(_bars(days, close, value, **kw), tickers=None)
    return mk, Arrays(mk)


def _order(t, qty, side=1, price=50.0, sigma=0.0, ticker="X"):
    return SimpleNamespace(order_id=1, decision_i=t, ticker=ticker, side=side, qty=qty,
                           arrival_price=price, sigma=sigma)


# ─── cost model ───────────────────────────────────────────────────────────────
def test_cost():
    cases = {1.99: 0.01, 2.0: 0.02, 9.95: 0.05, 10.0: 0.10, 25.0: 0.25, 100.0: 0.50, 200.0: 1.0, 400.0: 2.0}
    check("tick size follows SET table", all(cost.tick_size(p) == t for p, t in cases.items()))
    check("floor_lot", cost.floor_lot(250) == 200 and cost.floor_lot(99) == 0 and cost.floor_lot(np.nan) == 0)
    check("square-root impact", abs(cost.impact(50, 0.01, 1e6, 100e6, 1.0) - 0.01 * 0.1 * 50) < 1e-12
          and cost.impact(50, 0.01, 1e6, 0.0, 1.0) == 0.0)


# ─── engine on controlled markets ────────────────────────────────────────────
def test_flat_market_is_spread_plus_commission():
    mk, ar = _market()
    exp_spread = cost.tick_size(50.0) / 2 / 50.0 * 1e4
    exp_comm = C.COMMISSION_ALL_IN * (1 + exp_spread / 1e4) * 1e4
    ok, det = True, []
    for a in C.ALGOS:
        r, _ = execute(_order(T0, 20_000), a, ar, Params())
        good = (r["fill_rate"] == 1.0 and abs(r["timing_bps"]) < 1e-9 and abs(r["impact_bps"]) < 1e-9
                and abs(r["spread_bps"] - exp_spread) < 1e-9 and abs(r["commission_bps"] - exp_comm) < 1e-9)
        ok &= good
        det.append(f"{a} {r['is_bps']:.3f}")
    check("σ=0, flat price → IS = ½ spread + commission for every algo", ok, ", ".join(det))


def test_schedules():
    mk, ar = _market()
    t, Q = T0, 80_000
    _, f = execute(_order(t, Q), "MARKET", ar, Params(), keep_fills=True)
    check("MARKET: one fill, in bar t+1", len(f) == 1 and f[0]["bar"] == t + 1 and f[0]["qty"] == Q)
    _, f = execute(_order(t, Q), "TWAP", ar, Params(), keep_fills=True)
    check("TWAP: H equal slices over t+1 … t+H", [x["qty"] for x in f] == [Q // H] * H
          and [x["bar"] for x in f] == list(range(t + 1, t + 1 + H)))
    _, f = execute(_order(t, 1_000_000), "VWAP", ar, Params(schedule_cap=1.0), keep_fills=True)
    prof = mk.profile.loc[mk.days[t]]                      # profile known at the decision day's open
    w = np.array([prof[h] for h in mk.hours[t + 1: t + 1 + H]])
    got = np.array([x["qty"] for x in f]) / 1_000_000
    check("VWAP: slices follow the decision day's rolling profile", np.allclose(got, w / w.sum(), atol=2e-4),
          f"max dev {np.abs(got - w / w.sum()).max():.5f}")
    for algo in C.POV_SCHEDULES:
        _, f = execute(_order(t, 10_000_000), algo, ar, Params(), keep_fills=True)
        rates = [C.POV_SCHEDULES[algo][mk.hours[x["bar"]]] for x in f]
        check(f"{algo}: child = rate(bar hour) × bar value",
              len(f) == H and all(abs(x["qty"] * 50.0 - r * 200e6) < 50.0 * C.LOT for x, r in zip(f, rates)),
              f"rates {sorted(set(rates))}")
    _, f = execute(_order(t, 10_000_000), "POV5/10", ar, Params(), keep_fills=True)
    morning = [x["participation"] for x in f if mk.hours[x["bar"]] in C.MORNING_HOURS]
    afternoon = [x["participation"] for x in f if mk.hours[x["bar"]] in C.AFTERNOON_HOURS]
    check("POV5/10: 5 % in bars 10–13, 10 % in bars 14–17",
          morning and afternoon and np.allclose(morning, 0.05, atol=1e-3) and np.allclose(afternoon, 0.10, atol=1e-3))


def test_cap_and_catch_up():
    mk, ar = _market(value=20e6)            # cap 25 % → 5 M THB = 100k shares per bar
    r, f = execute(_order(T0, 1_000_000), "TWAP", ar, Params(), keep_fills=True)   # wants 125k/bar
    check("TWAP: capped at SCHEDULE_CAP × bar value", all(x["participation"] <= C.SCHEDULE_CAP + 1e-12 for x in f))
    check("TWAP: unfilled after horizon is cancelled (fill rate < 1)", r["fill_rate"] == H * 100_000 / 1_000_000,
          f"fill rate {r['fill_rate']:.3f}")
    # catch-up: a no-trade bar inside the window is made up later
    v = np.full(DAYS * NH, 200e6)
    v[T0 + 2] = 0.0
    mk2, ar2 = _market(value=v)
    r, f = execute(_order(T0, 80_000), "TWAP", ar2, Params(), keep_fills=True)
    check("TWAP: no-trade bar → nothing filled there, caught up next bar",
          r["fill_rate"] == 1.0 and T0 + 2 not in [x["bar"] for x in f] and f[1]["qty"] == 20_000,
          f"slices {[x['qty'] for x in f]}")


def test_timing_and_opportunity():
    c = np.full(DAYS * NH, 50.0)
    c[T0 + 1:] = 51.0
    mk, ar = _market(close=c)
    r, _ = execute(_order(T0, 10_000), "MARKET", ar, Params())
    check("buy, price +2 % after decision → timing +200 bps", abs(r["timing_bps"] - 200.0) < 1e-9)
    r, _ = execute(_order(T0, 10_000, side=-1), "MARKET", ar, Params())
    check("sell, price +2 % after decision → timing −200 bps (gain)", abs(r["timing_bps"] + 200.0) < 1e-9)
    mk, ar = _market(close=c, value=1e5)                 # tiny liquidity → POV cannot finish
    r, _ = execute(_order(T0, 100_000), "POV10", ar, Params())
    unfilled = 100_000 - r["filled"]
    exp = unfilled * (51.0 - 50.0) / (100_000 * 50.0) * 1e4
    check("opportunity = unfilled × s × (Close_{t+H} − arrival)", unfilled > 0 and abs(r["opportunity_bps"] - exp) < 1e-9,
          f"unfilled {unfilled}, opp {r['opportunity_bps']:.2f} bps")


def test_interval_vwap():
    c = np.linspace(50, 60, DAYS * NH)
    mk, ar = _market(close=c)
    r, _ = execute(_order(T0, 10_000, price=c[T0]), "TWAP", ar, Params())
    exp = H / (1.0 / c[T0 + 1:T0 + 1 + H]).sum()   # equal value per bar, vwap_bar = close → Σv/Σ(v/p) = harmonic mean
    check("interval VWAP = Σ value / Σ volume over t+1 … t+H", abs(r["interval_vwap"] - exp) < 1e-9)


# ─── data layer ───────────────────────────────────────────────────────────────
def test_data_layer():
    days = DAYS
    v = np.repeat(np.arange(1, days + 1) * 1e6, NH)           # daily value rises NH·1M, NH·2M, …
    mk = data.build_market(_bars(days, 50.0, v, tickers=("A",)), tickers=None)
    d21 = mk.adv.index[20]
    exp_a = np.mean(np.arange(1, 21) * NH * 1e6)              # days 1 … 20, NOT day 21
    check("ADV uses the previous ADV_DAYS days only (no look-ahead)",
          abs(mk.adv.loc[d21, "A"] - exp_a) < 1e-6 and np.isnan(mk.adv.iloc[19]["A"]))

    # rolling profile on random hourly values: compare with a direct numpy computation
    rng = np.random.default_rng(0)
    vals = rng.uniform(1e6, 2e6, (days, NH))
    bars = _bars(days, 50.0, vals.ravel())
    mk = data.build_market(bars, tickers=None)
    share = vals / vals.sum(axis=1, keepdims=True)
    d = 30
    exp = share[d - C.PROFILE_DAYS: d].mean(axis=0)
    exp = exp / exp.sum()
    got = mk.profile.iloc[d].to_numpy()
    check("rolling profile = mean share of the previous PROFILE_DAYS days", np.allclose(got, exp, atol=1e-12))
    bars2 = bars.copy()
    bars2.loc[d * NH: d * NH + NH - 1, "value"] *= rng.uniform(0.1, 10, NH)  # change day d itself
    mk2 = data.build_market(bars2, tickers=None)
    check("profile of day d does not use day d (no look-ahead)",
          np.allclose(mk2.profile.iloc[d], got) and not np.allclose(mk2.profile.iloc[d + 1], mk.profile.iloc[d + 1]))
    check("profile rows sum to 1; NaN during warm-up",
          np.allclose(mk.profile.dropna().sum(axis=1), 1.0) and mk.profile.iloc[: C.PROFILE_DAYS].isna().all().all()
          and list(mk.profile.columns) == C.SESSION_HOURS)

    c = np.full(days * NH, 50.0)
    c[40:] = 100.0
    mk2 = data.build_market(_bars(days, c, 1e6), tickers=None)
    check("jump flag on |hourly return| > JUMP_FILTER", bool(mk2.jump.iloc[40, 0]) and mk2.jump.sum().sum() == 1)
    b = _bars(days, 50.0, 1e6)
    b.loc[5, ["low", "high"]] = [49.0, 49.5]                  # vwap 50 outside → clipped to 49.5
    mk3 = data.build_market(b, tickers=None)
    check("bar VWAP clipped into [low, high]", mk3.vwap.iloc[5, 0] == 49.5)

    # a day without its 14:00 bar: inserted empty, close carried, still a full profile day
    b = _bars(days, 50.0, 1e6)
    miss = (b["dt"].dt.hour == 14) & (b["dt"].dt.normalize() <= b["dt"].dt.normalize().unique()[25])
    mk4 = data.build_market(b[~miss].reset_index(drop=True), tickers=None)
    i14 = int(np.flatnonzero(mk4.hours == 14)[3])
    check("missing 14:00 bar → inserted with value 0, close carried, not observed",
          len(mk4.close) == days * NH and mk4.value.iloc[i14, 0] == 0 and not mk4.observed.iloc[i14]
          and mk4.close.iloc[i14, 0] == mk4.close.iloc[i14 - 1, 0])
    check("days missing only 14:00 still feed the rolling profile (14:00 share = 0)",
          mk4.profile.iloc[C.PROFILE_DAYS:].notna().all().all()
          and abs(mk4.profile.iloc[C.PROFILE_DAYS + 1][14]) < 1e-12)


def test_holm():
    adj = stats.holm(np.array([0.01, 0.04, 0.03]))
    check("Holm adjustment", np.allclose(adj, [0.03, 0.06, 0.06]), str(adj))


# ─── real data ────────────────────────────────────────────────────────────────
def test_real_data():
    if not data.data_files():
        check("real data present (skipped — no SET50_*.csv)", True)
        return
    mk = data.load_market()
    ar = Arrays(mk)
    od, info = orders.generate(mk, n_base=150)
    check("market: exactly the 10 locked tickers, 8-bar grid every day",
          mk.tickers == C.TICKERS and mk.close.groupby(mk.days).size().eq(NH).all())
    check("orders: decisions only at observed bars", mk.observed.iloc[od["decision_i"]].all())
    first_ok = pd.Timestamp(mk.info["first_profile_day"])
    check("orders: only locked tickers, decisions after the profile/ADV warm-up",
          set(od["ticker"]) <= set(C.TICKERS) and od["decision_dt"].min() >= first_ok
          and od["decision_dt"].dt.year.nunique() == 4, f"first decision {od['decision_dt'].min()}")
    base = od.groupby("base_id")[["ticker", "side", "decision_i"]].nunique()
    check("orders: every size shares the same (time, ticker, side) draw",
          (base == 1).all().all() and od.groupby("base_id").size().eq(len(C.SIZE_BUCKETS_PCT_NAV)).all())
    check("orders: lot-sized, notional ≤ bucket × NAV",
          (od["qty"] % C.LOT == 0).all() and (od["paper_notional"] <= od["pct_nav"] * C.NAV_THB + 1e-6).all())
    jumps = mk.jump.to_numpy()
    col = {t: j for j, t in enumerate(mk.tickers)}
    check("orders: no corporate-action jump inside any window",
          not any(jumps[o.decision_i: o.decision_i + H + 1, col[o.ticker]].any() for o in od.itertuples()))
    res, fills = run(od, ar, keep_fills=True)
    check("every algo ran every order", res.groupby("algo")["order_id"].nunique().eq(len(od)).all())
    sched = fills[fills["algo"].isin(["TWAP", "VWAP"])]
    check("TWAP/VWAP children ≤ cap × bar value", (sched["participation"] <= C.SCHEDULE_CAP + 1e-9).all())
    pov = fills[fills.algo.isin(list(C.POV_SCHEDULES))].copy()
    pov["rate"] = [C.POV_SCHEDULES[a][h] for a, h in zip(pov["algo"], pd.to_datetime(pov["datetime"]).dt.hour)]
    check("POV children ≤ scheduled rate(hour) × bar value", (pov["participation"] <= pov["rate"] + 1e-9).all())
    check("fills only in bars t+1 … t+H", fills.merge(od[["order_id", "decision_i"]], on="order_id")
          .eval("bar > decision_i and bar <= decision_i + @H").all())
    agg = fills.groupby(["order_id", "algo"])["qty"].sum()
    check("Σ child qty = reported filled ≤ parent qty",
          (agg.reindex(pd.MultiIndex.from_frame(res[["order_id", "algo"]])).fillna(0).to_numpy()
           == res["filled"].to_numpy()).all() and (res["filled"] <= res["qty"]).all())
    parts = res[[f"{k}_bps" for k in ("timing", "spread", "impact", "commission", "opportunity")]].sum(axis=1)
    check("IS = Σ components", np.allclose(parts, res["is_bps"]))


if __name__ == "__main__":
    for fn in [test_cost, test_flat_market_is_spread_plus_commission, test_schedules, test_cap_and_catch_up,
               test_timing_and_opportunity, test_interval_vwap, test_data_layer, test_holm, test_real_data]:
        fn()
    width = max(len(n) for n, _, _ in _results)
    for name, ok, detail in _results:
        print(f"{'PASS' if ok else 'FAIL'}  {name:<{width}}  {detail}")
    failed = sum(not ok for _, ok, _ in _results)
    print(f"\n{len(_results) - failed}/{len(_results)} passed")
    raise SystemExit(1 if failed else 0)
