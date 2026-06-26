// ══════════════════════════════════════════════════════════════
// blacklitterman.js — the Black-Litterman core
//
//   Prior:          Π    = δ · Σ · w_mkt
//   Posterior Var:  M    = [(τΣ)⁻¹ + Pᵀ Ω⁻¹ P]⁻¹
//   Posterior Mean: μ_BL = M · [(τΣ)⁻¹ Π + Pᵀ Ω⁻¹ Q]
//   Total Cov:      Σ_BL = Σ + M
//   Optimal Weight: w*   = (δ · Σ_BL)⁻¹ · μ_BL   (then normalised)
// ══════════════════════════════════════════════════════════════

const BL = (() => {

  const { transpose, multiply, matVec, inverse, scale, add, diag, regularize, quadForm, dot } = Matrix;

  // Π = δ Σ w_mkt
  function impliedReturns(delta, sigma, wMkt) {
    return matVec(sigma, wMkt).map(x => x * delta);
  }

  // Full BL update. views = { P, Q, omega } where omega is a 1-D array
  // of diagonal variances (one per view). Returns { pi, muBL, sigmaBL, M }.
  // Diagonal loading added to Σ before inversion. Bigger than the bare
  // minimum (1e-4) so a near-singular covariance from highly-correlated
  // names doesn't make the inverse blow up. (BugFix #4)
  const DIAG_EPS = 1e-4;

  function compute({ delta, tau, sigma, wMkt, P, Q, omega }) {
    const n = sigma.length;
    const sig = regularize(sigma, DIAG_EPS);
    const pi = impliedReturns(delta, sig, wMkt);

    const tauSigmaInv = inverse(scale(sig, tau));

    let muBL, M;
    if (P && P.length) {
      const Pt = transpose(P);
      const omegaInv = inverse(regularize(diag(omega), 1e-12));

      // M = [(τΣ)⁻¹ + Pᵀ Ω⁻¹ P]⁻¹
      const PtOmInvP = multiply(multiply(Pt, omegaInv), P);
      M = inverse(add(tauSigmaInv, PtOmInvP));

      // μ_BL = M [(τΣ)⁻¹ Π + Pᵀ Ω⁻¹ Q]
      const term1 = matVec(tauSigmaInv, pi);
      const term2 = matVec(multiply(Pt, omegaInv), Q);
      muBL = matVec(M, term1.map((x, i) => x + term2[i]));
    } else {
      // no views → posterior collapses to the prior
      M = inverse(tauSigmaInv);
      muBL = pi.slice();
    }

    const sigmaBL = add(sig, M);
    return { pi, muBL, sigmaBL, M };
  }

  // w* = (δ Σ_BL)⁻¹ μ_BL — raw, un-normalised.
  // These are the UNCONSTRAINED weights (may be negative / concentrated);
  // pass them through constrainWeights() for a tradeable portfolio.
  // Note: intentionally not normalised here — dividing by a near-zero or
  // negative sum can flip signs and amplify extreme values. constrainWeights()
  // handles normalisation safely after the long-only clamp. (BugFix #2)
  function optimalWeights(delta, sigmaBL, muBL) {
    return matVec(inverse(scale(sigmaBL, delta)), muBL);
  }

  // Apply long-only + per-stock min/max constraints, renormalising to sum 1.
  // Uses iterative water-filling: cap over-weights and redistribute the
  // excess proportionally, floor under-weights and pull the deficit from the
  // rest — repeating until both hold. minW/maxW are clamped to what is
  // feasible for n stocks (n·minW ≤ 1, maxW ≥ 1/n). (BugFix #1, #2)
  function constrainWeights(wRaw, { longOnly = true, minW = 0, maxW = 1 } = {}) {
    const n = wRaw.length;
    let w = wRaw.slice();
    if (longOnly) w = w.map(x => Math.max(0, x));

    let s = w.reduce((a, b) => a + b, 0);
    w = s > 0 ? w.map(x => x / s) : w.map(() => 1 / n);

    const floorW = n * minW <= 1 ? minW : 0;     // skip floor if infeasible
    const capW = Math.max(maxW, 1 / n);          // can't cap below equal weight

    for (let iter = 0; iter < 200; iter++) {
      s = w.reduce((a, b) => a + b, 0);
      w = w.map(x => x / s);
      let changed = false;

      const over = w.map(x => x > capW + 1e-9);
      if (over.some(Boolean)) {
        const excess = w.reduce((a, x, i) => a + (over[i] ? x - capW : 0), 0);
        const freeSum = w.reduce((a, x, i) => a + (over[i] ? 0 : x), 0);
        w = w.map((x, i) => over[i] ? capW : (freeSum > 0 ? x + excess * (x / freeSum) : x));
        changed = true;
      }

      const under = w.map(x => x < floorW - 1e-9);
      if (floorW > 0 && under.some(Boolean)) {
        const deficit = under.reduce((a, u, i) => a + (u ? floorW - w[i] : 0), 0);
        const room = w.reduce((a, x, i) => a + (under[i] ? 0 : Math.max(x - floorW, 0)), 0);
        w = w.map((x, i) => under[i] ? floorW : (room > 0 ? x - deficit * (Math.max(x - floorW, 0) / room) : x));
        changed = true;
      }
      if (!changed) break;
    }
    s = w.reduce((a, b) => a + b, 0);
    return s > 0 ? w.map(x => x / s) : w;
  }

  // Gross leverage of the unconstrained weights: Σ|wᵢ|. >1 means the
  // optimiser wanted net short positions. (BugFix #9)
  function leverage(wRaw) {
    const total = wRaw.reduce((s, x) => s + x, 0) || 1;
    return wRaw.reduce((s, x) => s + Math.abs(x / total), 0);
  }

  // ── Portfolio analytics ──────────────────────────────────────
  function portfolioReturn(weights, mu) {
    return dot(weights, mu);
  }

  function portfolioVol(weights, sigma) {
    return Math.sqrt(Math.max(quadForm(weights, sigma), 0));
  }

  function sharpe(weights, mu, sigma, rf = 0) {
    const vol = portfolioVol(weights, sigma);
    return vol > 0 ? (portfolioReturn(weights, mu) - rf) / vol : 0;
  }

  // Tracking error of a portfolio vs the market portfolio.
  function trackingError(weights, wMkt, sigma) {
    const active = weights.map((w, i) => w - wMkt[i]);
    return Math.sqrt(Math.max(quadForm(active, sigma), 0));
  }

  // Random long-only portfolios for an efficient-frontier scatter.
  function randomPortfolios(mu, sigma, rf = 0, count = 1500) {
    const n = mu.length;
    const pts = [];
    for (let k = 0; k < count; k++) {
      const raw = Array.from({ length: n }, () => Math.random());
      const s = raw.reduce((a, b) => a + b, 0);
      const w = raw.map(x => x / s);
      pts.push({
        vol: portfolioVol(w, sigma),
        ret: portfolioReturn(w, mu),
        sharpe: sharpe(w, mu, sigma, rf),
        weights: w,
      });
    }
    return pts;
  }

  return {
    impliedReturns, compute, optimalWeights, constrainWeights, leverage,
    portfolioReturn, portfolioVol, sharpe, trackingError, randomPortfolios,
  };
})();

if (typeof window !== 'undefined') window.BL = BL;
