# Module 5: Black-Litterman Model (P, Q, Ω Construction + Posterior)

**Depends on:** Module 4 (22-stock universe with r_hat, omega, rank_in_sector)
**Produces output for:** Module 6 (Portfolio Optimization — needs μ_BL and Σ)

---

## 1. Goal

Given the 22 selected stocks and their ML-predicted returns/uncertainties, construct the Black-Litterman inputs (P, Q, Ω), combine with the market-implied prior (Π), and compute the posterior expected return vector μ_BL.

---

## 2. Notation Recap

- N = 22 (number of stocks in the universe at this rebalance date)
- K = number of views = 22 (11 absolute + 11 relative, see Section 4)
- Σ: N×N historical covariance matrix of the 22 stocks' returns
- w_mkt: N×1 market-cap weights of the 22 stocks (renormalized to sum to 1 within this subset)
- δ = 2.5 (risk aversion, fixed)
- τ = 0.05 (fixed)

---

## 3. Step 1: Compute Σ (Covariance Matrix)

```python
def compute_covariance(returns_df: pd.DataFrame, lookback_years: int = 10) -> np.ndarray:
    """
    returns_df: daily returns for the 22 selected tickers, sliced to the
                same rolling window used for ML training (consistency
                with Module 3's training window is intentional — both
                use the same 10-year lookback ending before the
                rebalance date).
    Returns: 22x22 covariance matrix (annualized or daily — pick one
             and be CONSISTENT with the units used for Q, Π, and the
             optimization in Module 6. Recommended: use DAILY returns
             for Σ, then annualize by multiplying by 252 when combining
             with Π and Q if those are expressed in 63-day terms — see
             Section 7 for the full unit-consistency requirement.)
    """
    return returns_df.cov().values
```

**This must use the same date range as the ML model's training window** (Module 3, Section 7) — both are "what we knew as of the rebalance date," so they should be computed over consistent historical periods. Do not use a different lookback for Σ than for the ML training data without an explicit reason.

---

## 4. Step 2: Construct P (View Matrix) and Q (View Returns)

The 22 stocks are organized as 11 sector pairs, each with a "top" stock (rank_in_sector == 1) and a "2nd" stock (rank_in_sector == 2), per Module 4's output.

### View ordering convention

Index the 22 stocks 0-21 in a fixed order (e.g., sorted by sector name, then by rank_in_sector). This ordering must be used consistently for P's columns, Q's rows, Σ's rows/columns, and the final weight vector w — a mismatch here silently corrupts every downstream calculation. Recommended: build an explicit `stock_order: List[str]` list once per rebalance date and pass it through every function in this module and Module 6.

### Views 1-11: Absolute views (one per sector, on the "top" stock)

For each sector s with top stock i:
```
P[s, :] = e_i        # one-hot vector, 1 at index i, 0 elsewhere
Q[s] = r_hat[i]       # the SVR-predicted return for that stock
```

### Views 12-22: Relative views (one per sector, top vs. 2nd)

For each sector s with top stock i and 2nd stock j:
```
P[11+s, :] = e_i - e_j     # +1 at index i, -1 at index j, 0 elsewhere
Q[11+s] = r_hat[i] - r_hat[j]
```

### Edge case: sector with no "2nd" stock (from Module 4, Section 3)

If a sector only produced 1 valid candidate, skip its relative view entirely. This reduces K below 22 for that rebalance date only — handle this as a variable-size P/Q/Ω rather than forcing a fixed 22 rows. Document the actual K used at each rebalance date in the output (Section 8).

### Implementation

```python
def construct_P_Q(universe_df: pd.DataFrame, stock_order: list) -> tuple:
    """
    universe_df: output of Module 4, columns [ticker, sector, r_hat, omega, rank_in_sector]
    stock_order: fixed ordering of the 22 (or fewer) tickers

    Returns: (P, Q) where P is (K, N) and Q is (K,)
    """
    N = len(stock_order)
    idx = {ticker: i for i, ticker in enumerate(stock_order)}
    P_rows = []
    Q_vals = []

    for sector, group in universe_df.groupby('sector'):
        top = group[group['rank_in_sector'] == 1]
        second = group[group['rank_in_sector'] == 2]

        if len(top) == 0:
            continue  # should not happen given Module 4's contract, but defensive

        i = idx[top.iloc[0]['ticker']]
        # Absolute view
        p_row = np.zeros(N)
        p_row[i] = 1
        P_rows.append(p_row)
        Q_vals.append(top.iloc[0]['r_hat'])

        if len(second) > 0:
            j = idx[second.iloc[0]['ticker']]
            # Relative view
            p_row_rel = np.zeros(N)
            p_row_rel[i] = 1
            p_row_rel[j] = -1
            P_rows.append(p_row_rel)
            Q_vals.append(top.iloc[0]['r_hat'] - second.iloc[0]['r_hat'])

    return np.array(P_rows), np.array(Q_vals)
```

---

## 5. Step 3: Construct Ω (Uncertainty Matrix)

Ω is diagonal. The 11 absolute views and (up to) 11 relative views are calibrated with **two separate scale factors** — this was an explicit design decision; do not collapse them into one global scale.

```python
def construct_omega(universe_df: pd.DataFrame, P: np.ndarray, tau_sigma: np.ndarray,
                     n_absolute: int) -> np.ndarray:
    """
    universe_df: as above, has 'omega' column (per-stock validation residual variance, from Module 3)
    P: (K, N) view matrix from Step 2
    tau_sigma: τΣ, the (N, N) scaled covariance matrix
    n_absolute: number of absolute views (= 11, or fewer if edge cases occurred)

    Returns: (K, K) diagonal Omega matrix
    """
    K = P.shape[0]
    raw_omega = np.zeros(K)

    # For absolute views: raw_omega[k] = omega_i (the single stock's residual variance)
    # For relative views: raw_omega[k] = omega_i + omega_j (sum, since the relative
    #                      view's error is the difference of two independent-ish errors)
    # (Use the omega values associated with the stocks indexed by the nonzero
    #  entries of each row of P to determine which case applies.)
    for k in range(K):
        nonzero_idx = np.nonzero(P[k])[0]
        omegas_for_view = [universe_df.iloc[idx]['omega'] for idx in nonzero_idx]
        # Note: this requires universe_df to be indexed in the same order as
        # stock_order used to build P — ensure this alignment carefully.
        raw_omega[k] = sum(omegas_for_view)

    # Two separate calibration scales
    abs_mask = np.arange(K) < n_absolute
    rel_mask = ~abs_mask

    diag_tau_sigma = np.diag(tau_sigma)

    # Absolute view calibration: match scale to the diagonal of τΣ for the
    # corresponding stocks
    alpha_abs = np.median(diag_tau_sigma) / np.median(raw_omega[abs_mask]) if abs_mask.any() else 1.0

    # Relative view calibration: match scale to the τΣ-implied variance of
    # the corresponding LONG-SHORT pair, i.e., P_row @ tau_sigma @ P_row.T
    # for each relative view row
    if rel_mask.any():
        rel_tau_sigma_implied = np.array([
            P[k] @ tau_sigma @ P[k].T for k in range(K) if rel_mask[k]
        ])
        alpha_rel = np.median(rel_tau_sigma_implied) / np.median(raw_omega[rel_mask])
    else:
        alpha_rel = 1.0

    calibrated_omega = raw_omega.copy()
    calibrated_omega[abs_mask] *= alpha_abs
    calibrated_omega[rel_mask] *= alpha_rel

    return np.diag(calibrated_omega)
```

**Why this matters (do not simplify away):** if a single global scale factor were used instead, the relative views (which tend to have lower raw residual variance because errors partially cancel when taking a difference) would end up systematically over- or under-weighted relative to the absolute views in the BL posterior. This was explicitly debated and rejected during design — implement the two-scale version as specified.

---

## 6. Step 4: Compute the Prior (Π)

```python
def compute_prior(Sigma: np.ndarray, w_mkt: np.ndarray, delta: float = 2.5) -> np.ndarray:
    """
    Sigma: NxN covariance matrix (same units as used in Step 1)
    w_mkt: Nx1 market-cap weights of the 22 stocks, renormalized to sum to 1
    delta: risk aversion coefficient
    Returns: Nx1 prior expected return vector Π
    """
    return delta * Sigma @ w_mkt
```

`w_mkt` here uses the market cap data from Module 1 (Section 3.3), filtered to only the 22 selected stocks, then renormalized so the 22 weights sum to 1 (since they're a subset of the full S&P 500, not the full market).

---

## 7. Unit Consistency — Read This Before Implementing

This is the single most likely place to introduce a silent, hard-to-debug bug. Q (from Step 2) is in **63-day return** units (since that's what the SVR predicts). Σ, if computed from **daily** returns (Step 1), will be in daily variance units. These must be reconciled before combining them in the posterior formula (Step 5).

**Recommended approach:** Annualize or rescale Σ to match the 63-day horizon before use:

```python
Sigma_63day = Sigma_daily * 63  # variance scales linearly with time under
                                  # the standard random-walk assumption
```

Apply this scaled Σ consistently everywhere downstream: in Π (Step 4), in τΣ (Step 5), and in Module 6's optimization. Do not mix daily-Σ in one place and 63-day-Q in another. Write an explicit unit test or assertion checking that Σ, Π, and Q are all on the same return-horizon basis before running the posterior calculation.

---

## 8. Step 5: Compute the BL Posterior

```python
def compute_bl_posterior(Sigma: np.ndarray, Pi: np.ndarray, P: np.ndarray,
                          Q: np.ndarray, Omega: np.ndarray, tau: float = 0.05) -> np.ndarray:
    """
    All inputs must be unit-consistent per Section 7.
    Returns: Nx1 posterior expected return vector, mu_BL
    """
    tau_sigma = tau * Sigma
    tau_sigma_inv = np.linalg.inv(tau_sigma)
    omega_inv = np.linalg.inv(Omega)

    A = tau_sigma_inv + P.T @ omega_inv @ P
    b = tau_sigma_inv @ Pi + P.T @ omega_inv @ Q

    mu_BL = np.linalg.solve(A, b)  # more numerically stable than explicit inverse
    return mu_BL
```

Use `np.linalg.solve` rather than computing `np.linalg.inv(A) @ b` explicitly — it's more numerically stable, especially as K and N grow or if Σ is close to singular (which can happen with only a 10-year window and 22 correlated stocks from the same 11 sectors).

---

## 9. Numerical Stability Checks

Before trusting the output of Step 5, implement these checks and log warnings (not crashes) if they fail:

1. **Condition number of Σ.** `np.linalg.cond(Sigma)` — if this exceeds ~1e10, consider a small ridge adjustment: `Sigma_reg = Sigma + epsilon * np.eye(N)` with a small epsilon (e.g., 1e-6 relative to Σ's scale).
2. **Condition number of Ω.** Since Ω is diagonal, this is just the ratio of max to min diagonal entries — large ratios indicate one view is being trusted vastly more than another, which is expected behavior but worth logging for sanity checking.
3. **Sanity bound on μ_BL.** If any entry of μ_BL is wildly outside the range of the input views (e.g., 5x larger than any r_hat or any Π entry), this likely indicates a unit mismatch (Section 7) or a numerical issue — log a warning with the rebalance date for manual inspection rather than silently proceeding.

---

## 10. Output Contract

```python
{
    'rebalance_date': date,
    'stock_order': List[str],          # the 22 (or fewer) tickers, in the fixed order used
    'mu_BL': np.ndarray,                # (N,) posterior expected returns
    'Sigma': np.ndarray,                 # (N, N) covariance matrix used (63-day-scaled)
    'P': np.ndarray,                     # (K, N)
    'Q': np.ndarray,                     # (K,)
    'Omega': np.ndarray,                 # (K, K)
    'n_absolute_views': int,             # actual count, may be < 11 due to edge cases
    'n_relative_views': int              # actual count, may be < 11
}
```

Stored as `bl_outputs/{rebalance_date}.npz` (numpy arrays) plus a small JSON sidecar for the metadata fields. Module 6 reads `mu_BL`, `Sigma`, and `stock_order` directly.
