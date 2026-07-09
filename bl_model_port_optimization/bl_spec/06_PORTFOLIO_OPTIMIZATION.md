# Module 6: Portfolio Optimization (Efficient Frontier + Max Sharpe)

**Depends on:** Module 5 (μ_BL and Σ for the 22-stock universe)
**Produces output for:** Module 7 (Backtest Engine — needs w*, the portfolio weights to hold)

---

## 1. Goal

Using the Black-Litterman posterior expected return (μ_BL) and covariance (Σ) from Module 5, compute:
1. The full **Efficient Frontier** (for visualization/reporting).
2. The **Max Sharpe portfolio** weights (w*), which is what actually gets backtested.

---

## 2. Efficient Frontier

For a range of target returns, solve the minimum-variance problem:

$$\min_w w^\top \Sigma w \quad \text{subject to} \quad w^\top \mu_{BL} = \bar{r}, \quad \mathbf{1}^\top w = 1$$

```python
import numpy as np
from scipy.optimize import minimize

def efficient_frontier(mu_BL: np.ndarray, Sigma: np.ndarray,
                        n_points: int = 50, allow_short: bool = False) -> pd.DataFrame:
    """
    Returns a DataFrame with columns [target_return, volatility, weights]
    tracing out the efficient frontier.
    """
    N = len(mu_BL)
    target_returns = np.linspace(mu_BL.min(), mu_BL.max(), n_points)

    results = []
    for r_target in target_returns:
        constraints = [
            {'type': 'eq', 'fun': lambda w: w @ mu_BL - r_target},
            {'type': 'eq', 'fun': lambda w: np.sum(w) - 1}
        ]
        bounds = None if allow_short else [(0, 1)] * N  # see Section 3 on short-selling
        w0 = np.ones(N) / N

        result = minimize(
            lambda w: w @ Sigma @ w,
            w0, method='SLSQP', bounds=bounds, constraints=constraints
        )

        if result.success:
            vol = np.sqrt(result.x @ Sigma @ result.x)
            results.append({'target_return': r_target, 'volatility': vol, 'weights': result.x})
        else:
            # Some target returns near the extremes of mu_BL's range may be
            # infeasible with long-only constraints — log and skip rather
            # than crash
            continue

    return pd.DataFrame(results)
```

---

## 3. Long-Only vs. Long-Short — Decision Needed

The code above defaults to **long-only** (`bounds = [(0,1)]*N`), which is the standard assumption for a typical equity portfolio and is **recommended as the default** for this project unless there's a specific reason to allow shorting individual stocks. The relative views in Module 5 (top vs. 2nd stock within a sector) inform the *relative* expected returns used in μ_BL, but that does not require the resulting *portfolio* itself to take short positions — μ_BL feeds into a standard long-only mean-variance optimization just like any other expected-return estimate would.

If long-short is desired instead (e.g., to more directly express the relative sector views as long/short pairs), this needs to be an explicit decision, not a default — flag in `09_OPEN_DECISIONS.md` if Claude Code or the user wants to revisit this.

---

## 4. Max Sharpe Portfolio

```python
def max_sharpe_portfolio(mu_BL: np.ndarray, Sigma: np.ndarray,
                          risk_free_rate: float = 0.0, allow_short: bool = False) -> np.ndarray:
    """
    Returns: (N,) weight vector w* maximizing Sharpe ratio
    """
    N = len(mu_BL)

    def neg_sharpe(w):
        ret = w @ mu_BL
        vol = np.sqrt(w @ Sigma @ w)
        return -(ret - risk_free_rate) / vol

    constraints = [{'type': 'eq', 'fun': lambda w: np.sum(w) - 1}]
    bounds = None if allow_short else [(0, 1)] * N
    w0 = np.ones(N) / N

    result = minimize(neg_sharpe, w0, method='SLSQP', bounds=bounds, constraints=constraints)

    if not result.success:
        raise RuntimeError(f"Max Sharpe optimization failed: {result.message}")

    return result.x
```

`risk_free_rate` should be expressed in the **same 63-day-return units as μ_BL** (per Module 5, Section 7's unit consistency requirement) — e.g., if using a 3-month T-bill rate, convert from annualized to the 63-trading-day equivalent before passing in here: `rf_63day = (1 + rf_annual) ** (63/252) - 1`.

---

## 5. Closed-Form Alternative (Sanity Check, Not Primary Method)

The unconstrained closed-form solution `w* = (δΣ)⁻¹μ_BL` (renormalized to sum to 1) was mentioned during design as a simpler alternative. **Use this only as a sanity check against the constrained optimizer's output, not as the primary method** — it can produce negative weights (implicit shorting) even when long-only was intended, and doesn't respect the sum-to-one constraint without manual renormalization. If the two methods disagree substantially, investigate before trusting either.

```python
def closed_form_weights(mu_BL: np.ndarray, Sigma: np.ndarray, delta: float = 2.5) -> np.ndarray:
    w_raw = np.linalg.solve(delta * Sigma, mu_BL)
    return w_raw / np.sum(w_raw)  # renormalize; may contain negative entries
```

---

## 6. Output Contract

```python
{
    'rebalance_date': date,
    'stock_order': List[str],
    'frontier': pd.DataFrame,     # [target_return, volatility, weights] for plotting
    'w_star': np.ndarray,          # (N,) max Sharpe weights — this is what gets backtested
    'w_star_sharpe': float          # the achieved Sharpe ratio at w_star, for diagnostics
}
```

Stored as `portfolios/{rebalance_date}.npz` plus the frontier as `portfolios/{rebalance_date}_frontier.parquet`. Module 7 reads `w_star` and `stock_order` directly to execute the rebalance.
