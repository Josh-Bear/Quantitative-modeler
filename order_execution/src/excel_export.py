"""excel_export.py — 7-sheet workbook."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from . import constants as C

HEADER_FILL = PatternFill("solid", fgColor="1F3864")
HEADER_FONT = Font(bold=True, color="FFFFFF")

# row label → (description, number format)
COMPARISON_LABELS = {
    "n_slices": ("Slices per order", "0"),
    "n_orders": ("Parent orders", "0"),
    "n_buy": ("  of which BUY", "0"),
    "n_sell": ("  of which SELL", "0"),
    "pretrade_rejects": ("Pre-trade rejects", "0"),
    "pretrade_adjusts": ("Pre-trade adjustments", "0"),
    "traded_notional": ("Traded value (THB)", "#,##0"),
    "fill_rate_avg": ("Fill rate — avg per order", "0.00%"),
    "fill_rate_value_wtd": ("Fill rate — value weighted", "0.00%"),
    "is_bps_value_wtd": ("Implementation shortfall (bps, value wtd)", "0.00"),
    "timing_bps_value_wtd": ("  timing / drift", "0.00"),
    "spread_bps_value_wtd": ("  half spread", "0.00"),
    "impact_bps_value_wtd": ("  market impact", "0.00"),
    "commission_bps_value_wtd": ("  commission + VAT", "0.00"),
    "opportunity_bps_value_wtd": ("  opportunity (unfilled)", "0.00"),
    "is_bps_mean": ("IS mean per order (bps)", "0.00"),
    "is_bps_median": ("IS median per order (bps)", "0.00"),
    "is_bps_std": ("IS std per order (bps) — risk", "0.00"),
    "total_cost_thb": ("Total execution cost (THB)", "#,##0"),
    "vs_twap_bps_mean": ("Avg fill vs TWAP benchmark (bps)", "0.00"),
    "vs_vwap_bps_mean": ("Avg fill vs market VWAP (bps)", "0.00"),
    "bars_to_complete_avg": ("Bars from decision to last fill (avg)", "0.00"),
    "start_nav": ("Start NAV (THB)", "#,##0"),
    "final_nav": ("Final NAV (THB)", "#,##0"),
    "total_return": ("Total return", "0.00%"),
    "ann_vol": ("Annualised volatility", "0.00%"),
    "sharpe": ("Sharpe (annualised)", "0.00"),
    "max_drawdown": ("Max drawdown", "0.00%"),
    "turnover": ("Turnover (× avg NAV)", "0.00"),
}


def _style(ws, df: pd.DataFrame, formats: dict[str, str] | None = None):
    for c in ws[1]:
        c.fill, c.font = HEADER_FILL, HEADER_FONT
    ws.freeze_panes = "B2"
    for j, col in enumerate(df.columns, start=1):
        width = max(len(str(col)), *(len(str(v)) for v in df[col].head(200))) if len(df) else len(str(col))
        ws.column_dimensions[get_column_letter(j)].width = min(max(width + 2, 10), 45)
        fmt = (formats or {}).get(col)
        if fmt:
            for cell in ws[get_column_letter(j)][1:]:
                cell.number_format = fmt


def config_table() -> pd.DataFrame:
    keys = ["DATA_GLOB", "TICKERS", "SESSION_HOURS", "INITIAL_NAV", "INITIAL_CASH_PCT", "W_MIN", "W_MAX", "REBAL_BAND", "SMA_FAST", "SMA_SLOW", "RSI_LEN",
            "RSI_BUY_MAX", "RSI_SELL", "BUY_CONFIRM_BARS", "ATR_LEN", "K_DW", "DW_MIN", "DW_MAX",
            "LOT", "MIN_ORDER_THB", "STRATEGIES", "BENCH_BARS", "PARTICIPATION_CAP",
            "SPREAD_TICKS", "IMPACT_Y",
            "SIGMA_LEN", "COMMISSION", "VAT"]
    return pd.DataFrame({"parameter": keys, "value": [str(getattr(C, k)) for k in keys]})


def write_workbook(path: Path, signals: pd.DataFrame, pretrade_log: pd.DataFrame,
                   orders: pd.DataFrame, fills: pd.DataFrame, comp: pd.DataFrame,
                   nav: pd.DataFrame, data_info: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    comp_out = comp.loc[[k for k in COMPARISON_LABELS if k in comp.index]].copy()
    comp_out.insert(0, "metric", [COMPARISON_LABELS[k][0] for k in comp_out.index])
    cfg = pd.concat([config_table(),
                     pd.DataFrame({"parameter": [f"data.{k}" for k in data_info],
                                   "value": [str(v) for v in data_info.values()]})], ignore_index=True)
    sheets = {
        "Execution_Comparison": comp_out.reset_index(drop=True),
        "Signals": signals,
        "PreTrade_Log": pretrade_log,
        "Orders": orders,
        "Fills": fills,
        "Portfolio_NAV": nav,
        "Config": cfg,
    }
    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        for name, df in sheets.items():
            df.to_excel(xw, sheet_name=name, index=False)
        # number formats
        ws = xw.sheets["Execution_Comparison"]
        _style(ws, sheets["Execution_Comparison"])
        ws.column_dimensions["A"].width = 44
        for r, key in enumerate(comp_out.index, start=2):
            for c in range(2, comp_out.shape[1] + 1):
                ws.cell(row=r, column=c).number_format = COMPARISON_LABELS[key][1]
        _style(xw.sheets["Signals"], signals, {"dw": "0.00%", "close": "0.00", "rsi": "0.0"})
        _style(xw.sheets["PreTrade_Log"], pretrade_log)
        _style(xw.sheets["Orders"], orders, {
            "current_w": "0.00%", "target_w": "0.00%", "fill_rate": "0.00%", "is_bps": "0.00",
            "avg_fill_price": "0.0000", "twap_benchmark": "0.0000", "vwap_benchmark": "0.0000",
            "vs_twap_bps": "0.00", "vs_vwap_bps": "0.00", "paper_notional": "#,##0", "is_thb": "#,##0"})
        _style(xw.sheets["Fills"], fills, {"exec_price": "0.0000", "notional": "#,##0",
                                           "commission": "#,##0.00", "cash_flow": "#,##0"})
        _style(xw.sheets["Portfolio_NAV"], nav, {"nav_MARKET": "#,##0", "nav_TWAP": "#,##0"})
        _style(xw.sheets["Config"], cfg)
    return path
