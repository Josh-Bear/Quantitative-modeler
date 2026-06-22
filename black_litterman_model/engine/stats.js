// ══════════════════════════════════════════════════════════════
// stats.js — returns, covariance and signal computation
// Works on monthly price series; covariance/returns are ANNUALISED
// (×12 / mean×12) so Π, μ_BL and weights read in annual terms.
// ══════════════════════════════════════════════════════════════

const Stats = (() => {

  const MONTHS_PER_YEAR = 12;

  // Align several {date, close}[] series onto their common dates.
  // Returns { dates: [...], prices: { TICKER: [closes...] } } sorted ascending.
  function alignPrices(pricesByTicker) {
    const tickers = Object.keys(pricesByTicker);
    if (!tickers.length) return { dates: [], prices: {} };

    // intersection of dates present in every ticker
    let common = null;
    for (const t of tickers) {
      const dset = new Set(pricesByTicker[t].map(p => p.date));
      common = common === null ? dset : new Set([...common].filter(d => dset.has(d)));
    }
    const dates = [...common].sort();

    const prices = {};
    for (const t of tickers) {
      const map = new Map(pricesByTicker[t].map(p => [p.date, p.close]));
      prices[t] = dates.map(d => map.get(d));
    }
    return { dates, prices };
  }

  // Simple monthly returns for one price series.
  function returns(series) {
    const r = [];
    for (let i = 1; i < series.length; i++) r.push(series[i] / series[i - 1] - 1);
    return r;
  }

  // Returns matrix: rows = periods, cols = tickers (in `tickers` order).
  function returnsMatrix(prices, tickers) {
    const cols = tickers.map(t => returns(prices[t]));
    const periods = cols[0]?.length || 0;
    const R = [];
    for (let i = 0; i < periods; i++) R.push(cols.map(c => c[i]));
    return R;
  }

  function mean(arr) {
    return arr.reduce((s, x) => s + x, 0) / arr.length;
  }

  // Annualised sample covariance matrix from a returns matrix.
  function covariance(R) {
    const periods = R.length;
    const n = R[0].length;
    const means = [];
    for (let j = 0; j < n; j++) means.push(mean(R.map(row => row[j])));

    const cov = Matrix.zeros(n, n);
    for (let i = 0; i < n; i++)
      for (let j = 0; j < n; j++) {
        let s = 0;
        for (let t = 0; t < periods; t++)
          s += (R[t][i] - means[i]) * (R[t][j] - means[j]);
        cov[i][j] = (s / (periods - 1)) * MONTHS_PER_YEAR;  // annualise
      }
    return cov;
  }

  // Market-cap weights, in the given ticker order.
  function marketWeights(marketCap, tickers) {
    const caps = tickers.map(t => marketCap[t] || 0);
    const total = caps.reduce((s, c) => s + c, 0);
    return total > 0 ? caps.map(c => c / total) : caps.map(() => 1 / tickers.length);
  }

  function annualVol(R, j) {
    const col = R.map(row => row[j]);
    const m = mean(col);
    const variance = col.reduce((s, x) => s + (x - m) ** 2, 0) / (col.length - 1);
    return Math.sqrt(variance * MONTHS_PER_YEAR);
  }

  // ── Signals ───────────────────────────────────────────────────
  // Each returns one value per ticker (in `tickers` order).

  // Momentum = trailing 12m return − most recent 1m return.
  function momentum(prices, tickers) {
    return tickers.map(t => {
      const s = prices[t];
      const n = s.length;
      if (n < 13) return 0;
      const ret12 = s[n - 1] / s[n - 13] - 1;
      const ret1 = s[n - 1] / s[n - 2] - 1;
      return ret12 - ret1;
    });
  }

  // Mean-reversion z-score: how far the latest monthly return sits from its
  // historical mean, in standard deviations (negative → recent underperformance
  // → mean-reversion upside). Uses returns (stationary) instead of price
  // levels (non-stationary) to avoid trending assets always showing high z.
  function zScore(prices, tickers) {
    return tickers.map(t => {
      const rets = returns(prices[t]);   // monthly log-style simple returns
      if (!rets.length) return 0;
      const m = mean(rets);
      const sd = Math.sqrt(rets.reduce((a, x) => a + (x - m) ** 2, 0) / rets.length) || 1;
      return (rets[rets.length - 1] - m) / sd;  // last month vs historical mean
    });
  }

  // Relative strength: trailing 12m return ranked within the group,
  // centred around 0 (best = +, worst = −).
  function relativeStrength(prices, tickers) {
    const r12 = tickers.map(t => {
      const s = prices[t];
      return s.length >= 13 ? s[s.length - 1] / s[s.length - 13] - 1 : 0;
    });
    const m = mean(r12);
    return r12.map(x => x - m);
  }

  return {
    alignPrices, returns, returnsMatrix, covariance,
    marketWeights, annualVol, momentum, zScore, relativeStrength, mean,
  };
})();

if (typeof window !== 'undefined') window.Stats = Stats;
