"""
Apple DCF Model — Excel Workbook Builder
==========================================
Generates a 24-tab professional DCF model in Excel.
"""

import numpy as np
from openpyxl import Workbook
from openpyxl.utils import get_column_letter

from constants import (
    COMPANY, TICKER, CURRENCY, HIST_YEARS, PROJ_YEARS, ALL_YEARS,
    HIST_INCOME, HIST_BALANCE, HIST_OTHER, HIST_SEGMENTS,
    SCENARIOS, SEGMENT_GP_DIFF, SEGMENT_COMPARABLES,
    WC_ASSUMPTIONS, TGR_OFFSET, WACC_ADJ_BPS, RATIONALE, FALLBACK,
)
from formatters import (
    write_section_header, write_subheader, write_row_data, write_year_headers,
    write_scenario_headers, add_comment, set_col_widths, format_divider_tab,
    auto_width,
    FONT_TITLE, FONT_SUBTITLE, FONT_HEADER, FONT_SUBHEADER, FONT_LABEL,
    FONT_LABEL_B, FONT_VALUE, FONT_VALUE_B, FONT_SMALL, FONT_KPI,
    FONT_WARNING, FONT_CHECK_OK,
    FILL_HEADER, FILL_SUBHEADER, FILL_INPUT, FILL_CALC, FILL_HIGHLIGHT,
    FILL_WARNING, FILL_SCENARIO_B, FILL_SCENARIO_M, FILL_SCENARIO_W,
    FILL_WHITE, FILL_DIVIDER,
    BORDER_THIN, BORDER_BOTTOM, BORDER_TOP, BORDER_TB,
    ALIGN_LEFT, ALIGN_CENTER, ALIGN_RIGHT,
    FMT_NUM, FMT_NUM1, FMT_PCT, FMT_PCT2, FMT_MONEY, FMT_MONEY2,
    FMT_DEC2, FMT_DAYS,
    C_NAVY, C_DARK_BLUE, C_MED_BLUE,
)

SCENARIO_NAMES = ["Best", "Base", "Worst"]
NH = len(HIST_YEARS)   # 5
NP = len(PROJ_YEARS)   # 10


class AppleDCFModel:
    """Builds the complete Apple DCF Excel workbook."""

    def __init__(self, data: dict):
        self.data  = data
        self.wb    = Workbook()
        self.wb.remove(self.wb.active)  # remove default sheet

        # Unpack data
        self.market  = data["market"]
        self.macro   = data["macro"]
        self.fin     = data["financials"]
        self.seg     = data["segments"]
        self.derived = data["derived"]

        # Pre-compute all projections
        self._compute_projections()

    # ═══════════════════════════════════════════════════════════
    #  MASTER BUILD
    # ═══════════════════════════════════════════════════════════

    def build(self, output_path: str):
        """Build all 24 tabs and save."""
        self._build_cover()
        self._build_drivers()
        self._build_divider("Input -->")
        self._build_pl_input()
        self._build_bs_input()
        self._build_divider("Workings -->")
        for seg in ["iPhone", "Mac", "iPad", "Wearables"]:
            self._build_segment_tab(seg)
        self._build_services_tab()
        self._build_revenue_gp_summary()
        self._build_opex()
        self._build_ppe()
        self._build_working_capital()
        self._build_financing_wacc()
        self._build_divider("Output -->")
        self._build_pl_output()
        self._build_bs_output()
        self._build_cash_flow()
        self._build_dcf()
        self._build_sensitivity()
        self._build_scenario_summary()
        self._build_notes()

        self.wb.save(output_path)
        return self.proj  # return projections for QA / summary

    # ═══════════════════════════════════════════════════════════
    #  PRE-COMPUTATION (all scenarios)
    # ═══════════════════════════════════════════════════════════

    def _compute_projections(self):
        """Compute all forecast values for all 3 scenarios."""
        self.proj = {}
        for sc in SCENARIO_NAMES:
            self.proj[sc] = self._project_scenario(sc)

    def _project_scenario(self, sc: str) -> dict:
        """Full projection for one scenario."""
        p = {}

        # ── Segment Revenue ──
        seg_rev = {}
        for seg_name in ["iPhone", "Mac", "iPad", "Wearables", "Services"]:
            hist   = self.seg.get(seg_name, HIST_SEGMENTS[seg_name])
            last   = hist[-1] if hist else 0
            growth_key = f"{seg_name}_growth"
            growth = SCENARIOS.get(growth_key, {}).get(sc, [0.02]*NP)
            proj_vals = []
            prev = last
            for g in growth:
                prev = prev * (1 + g)
                proj_vals.append(round(prev, 1))
            seg_rev[seg_name] = proj_vals

        p["seg_rev"] = seg_rev
        p["products_rev"] = [sum(seg_rev[s][i] for s in ["iPhone","Mac","iPad","Wearables"])
                             for i in range(NP)]
        p["services_rev"] = seg_rev["Services"]
        p["total_rev"]    = [p["products_rev"][i] + p["services_rev"][i] for i in range(NP)]

        # ── GP% and Gross Profit ──
        prod_gp_pct = SCENARIOS["products_gp_pct"][sc]
        serv_gp_pct = SCENARIOS["services_gp_pct"][sc]
        p["products_gp_pct"] = prod_gp_pct
        p["services_gp_pct"] = serv_gp_pct
        p["products_cogs"] = [round(r * (1 - prod_gp_pct), 1) for r in p["products_rev"]]
        p["services_cogs"] = [round(r * (1 - serv_gp_pct), 1) for r in p["services_rev"]]
        p["total_cogs"]    = [p["products_cogs"][i] + p["services_cogs"][i] for i in range(NP)]
        p["gross_profit"]  = [p["total_rev"][i] - p["total_cogs"][i] for i in range(NP)]
        p["overall_gp_pct"]= [p["gross_profit"][i] / p["total_rev"][i] if p["total_rev"][i] else 0
                              for i in range(NP)]

        # ── Segment GP ──
        seg_gp = {}
        for seg_name in ["iPhone", "Mac", "iPad", "Wearables"]:
            diff  = SEGMENT_GP_DIFF.get(seg_name, 0)
            gp_pct = prod_gp_pct + diff
            seg_gp[seg_name] = {
                "gp_pct": gp_pct,
                "gp": [round(r * gp_pct, 1) for r in seg_rev[seg_name]],
            }
        seg_gp["Services"] = {
            "gp_pct": serv_gp_pct,
            "gp": [round(r * serv_gp_pct, 1) for r in seg_rev["Services"]],
        }
        p["seg_gp"] = seg_gp

        # ── OpEx ──
        rd_pct   = SCENARIOS["rd_pct_rev"][sc]
        sga_pct  = SCENARIOS["sga_pct_rev"][sc]
        p["rd_expense"]  = [round(r * rd_pct, 1) for r in p["total_rev"]]
        p["sga_expense"] = [round(r * sga_pct, 1) for r in p["total_rev"]]
        p["total_opex"]  = [p["rd_expense"][i] + p["sga_expense"][i] for i in range(NP)]
        p["operating_income"] = [p["gross_profit"][i] - p["total_opex"][i] for i in range(NP)]

        # ── Other Income (flat assumption from last historical) ──
        last_other = HIST_INCOME["other_income_expense"][-1]
        p["other_income"] = [last_other] * NP
        p["pretax_income"] = [p["operating_income"][i] + p["other_income"][i] for i in range(NP)]

        # ── Tax ──
        tax_rate = self.derived.get("effective_tax_rate", FALLBACK["effective_tax_rate"])
        p["tax_rate"] = tax_rate
        p["tax_provision"] = [round(max(0, pt * tax_rate), 1) for pt in p["pretax_income"]]
        p["net_income"]    = [p["pretax_income"][i] - p["tax_provision"][i] for i in range(NP)]

        # ── PP&E / D&A / CapEx ──
        capex_pct = SCENARIOS["capex_pct_rev"][sc]
        da_pct    = SCENARIOS["da_pct_ppe"][sc]
        last_ppe  = HIST_BALANCE["ppe_net"][-1]
        p["capex"] = [round(r * capex_pct, 1) for r in p["total_rev"]]
        ppe_vals = []
        da_vals  = []
        prev_ppe = last_ppe
        for i in range(NP):
            da  = round(prev_ppe * da_pct, 1)
            end_ppe = prev_ppe + p["capex"][i] - da
            da_vals.append(da)
            ppe_vals.append(round(end_ppe, 1))
            prev_ppe = end_ppe
        p["depreciation"] = da_vals
        p["ppe_net"]      = ppe_vals

        # ── Working Capital ──
        dso = WC_ASSUMPTIONS["dso"][sc]
        dio = WC_ASSUMPTIONS["dio"][sc]
        dpo = WC_ASSUMPTIONS["dpo"][sc]
        p["dso"], p["dio"], p["dpo"] = dso, dio, dpo
        p["accounts_receivable"] = [round(r * dso / 365, 1) for r in p["total_rev"]]
        p["inventory"]           = [round(c * dio / 365, 1) for c in p["total_cogs"]]
        p["accounts_payable"]    = [round(c * dpo / 365, 1) for c in p["total_cogs"]]
        p["nwc"] = [p["accounts_receivable"][i] + p["inventory"][i] - p["accounts_payable"][i]
                    for i in range(NP)]

        # Change in NWC (increase = cash outflow, so positive delta_nwc = negative for FCF)
        last_nwc = (HIST_BALANCE["accounts_receivable"][-1]
                    + HIST_BALANCE["inventory"][-1]
                    - HIST_BALANCE["accounts_payable"][-1])
        p["delta_nwc"] = []
        prev_nwc = last_nwc
        for i in range(NP):
            delta = p["nwc"][i] - prev_nwc
            p["delta_nwc"].append(round(delta, 1))
            prev_nwc = p["nwc"][i]

        # ── WACC ──
        rf   = self.macro.get("risk_free_rate",      FALLBACK["risk_free_rate"])
        mrp  = self.macro.get("market_risk_premium",  FALLBACK["market_risk_premium"])
        beta = self.market.get("beta",                FALLBACK["beta"])
        ke   = rf + beta * mrp
        kd   = self.derived.get("cost_of_debt",      FALLBACK["cost_of_debt"])

        # Capital structure (market equity + book debt)
        mkt_equity = self.market["share_price"] * self.market["shares_outstanding"]
        total_debt = HIST_BALANCE["long_term_debt"][-1] + HIST_BALANCE.get("short_term_debt", [0]*5)[-1]
        total_cap  = mkt_equity + total_debt
        we = mkt_equity / total_cap
        wd = total_debt / total_cap

        base_wacc = we * ke + wd * kd * (1 - tax_rate)
        wacc_adj  = WACC_ADJ_BPS[sc] / 10000
        wacc      = base_wacc + wacc_adj

        p["ke"]   = round(ke, 4)
        p["kd"]   = round(kd, 4)
        p["we"]   = round(we, 4)
        p["wd"]   = round(wd, 4)
        p["wacc"] = round(wacc, 4)

        # ── Terminal Growth Rate ──
        inflation = self.macro.get("expected_inflation", FALLBACK["expected_inflation"])
        tgr = inflation + TGR_OFFSET[sc]
        p["tgr"] = round(tgr, 4)

        # ── FCF (Unlevered) ──
        p["nopat"] = [round(p["operating_income"][i] * (1 - tax_rate), 1) for i in range(NP)]
        p["ufcf"]  = [round(p["nopat"][i] + p["depreciation"][i]
                            - p["capex"][i] - p["delta_nwc"][i], 1) for i in range(NP)]

        # ── DCF ──
        discount_factors = [1 / (1 + wacc)**t for t in range(1, NP + 1)]
        pv_fcf = [p["ufcf"][i] * discount_factors[i] for i in range(NP)]
        sum_pv_fcf = sum(pv_fcf)

        # Terminal Value (Gordon Growth)
        last_ufcf = p["ufcf"][-1]
        if wacc > tgr:
            tv = last_ufcf * (1 + tgr) / (wacc - tgr)
        else:
            tv = last_ufcf * 25  # fallback: 25x multiple
        pv_tv = tv * discount_factors[-1]
        ev    = sum_pv_fcf + pv_tv

        # Equity Bridge
        cash  = (HIST_BALANCE["cash_and_equivalents"][-1]
                 + HIST_BALANCE["short_term_investments"][-1])
        debt  = (HIST_BALANCE["long_term_debt"][-1]
                 + HIST_BALANCE["short_term_debt"][-1])
        equity_value = ev + cash - debt
        shares = self.market["shares_outstanding"]
        implied_price = equity_value / shares

        p["discount_factors"] = discount_factors
        p["pv_fcf"]     = pv_fcf
        p["sum_pv_fcf"] = round(sum_pv_fcf, 1)
        p["tv"]         = round(tv, 1)
        p["pv_tv"]      = round(pv_tv, 1)
        p["ev"]         = round(ev, 1)
        p["cash_bs"]    = cash
        p["debt_bs"]    = debt
        p["equity_value"]  = round(equity_value, 1)
        p["implied_price"] = round(implied_price, 2)
        p["tv_pct_ev"]     = round(pv_tv / ev * 100, 1) if ev else 0

        # ── Balance Sheet projections (simplified) ──
        p["total_current_assets"] = [
            round(p["accounts_receivable"][i] + p["inventory"][i] + cash * 1.02**i, 1)
            for i in range(NP)]
        p["total_assets"] = [
            round(p["total_current_assets"][i] + p["ppe_net"][i]
                  + HIST_BALANCE["other_non_current_assets"][-1], 1)
            for i in range(NP)]
        p["total_current_liabilities"] = [
            round(p["accounts_payable"][i]
                  + HIST_BALANCE["other_current_liabilities"][-1] * 1.01**i, 1)
            for i in range(NP)]
        p["total_liabilities"] = [
            round(p["total_current_liabilities"][i]
                  + debt * (0.97**i)  # gradual debt paydown
                  + HIST_BALANCE["other_non_current_liabilities"][-1], 1)
            for i in range(NP)]
        p["stockholders_equity"] = [
            round(p["total_assets"][i] - p["total_liabilities"][i], 1)
            for i in range(NP)]

        return p

    # ═══════════════════════════════════════════════════════════
    #  TAB BUILDERS
    # ═══════════════════════════════════════════════════════════

    def _build_cover(self):
        ws = self.wb.create_sheet("Cover")
        ws.sheet_properties.tabColor = C_NAVY
        set_col_widths(ws, {1: 5, 2: 50, 3: 30})

        from datetime import datetime
        ws.cell(row=3,  column=2, value=COMPANY).font = FONT_TITLE
        ws.cell(row=5,  column=2, value="Discounted Cash Flow Model").font = FONT_SUBTITLE
        ws.cell(row=7,  column=2, value=f"Ticker: {TICKER}").font = FONT_LABEL
        ws.cell(row=8,  column=2, value=f"Currency: {CURRENCY}").font = FONT_LABEL
        ws.cell(row=9,  column=2, value=f"All values in USD millions unless stated").font = FONT_SMALL
        ws.cell(row=11, column=2, value=f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}").font = FONT_SMALL
        ws.cell(row=13, column=2, value="10-Year Forecast  •  3 Scenarios (Best / Base / Worst)").font = FONT_LABEL_B
        ws.cell(row=15, column=2, value="Data Sources:").font = FONT_SUBHEADER
        ws.cell(row=16, column=2, value="• SEC EDGAR XBRL API (10-K filings)").font = FONT_LABEL
        ws.cell(row=17, column=2, value="• Yahoo Finance (market data)").font = FONT_LABEL
        ws.cell(row=18, column=2, value="• FRED (risk-free rate, inflation)").font = FONT_LABEL
        ws.cell(row=19, column=2, value="• Damodaran (market risk premium)").font = FONT_LABEL

    def _build_divider(self, title):
        ws = self.wb.create_sheet(title)
        format_divider_tab(ws, title)

    def _build_drivers(self):
        ws = self.wb.create_sheet("Drivers")
        ws.sheet_properties.tabColor = C_MED_BLUE
        set_col_widths(ws, {1: 5, 2: 35, 3: 18, 4: 30})

        r = 1
        write_section_header(ws, r, 2, 4, "Model Drivers & Assumptions"); r += 2

        # Market data
        write_subheader(ws, r, 2, 4, "Market Data"); r += 1
        drivers = [
            ("Company",                  COMPANY,                              "Static"),
            ("Ticker",                   TICKER,                               "Static"),
            ("Currency",                 CURRENCY,                             "Static"),
            ("Share Price (latest)",     self.market["share_price"],            "Yahoo Finance"),
            ("Shares Outstanding (mn)",  self.market["shares_outstanding"],     "Yahoo Finance"),
            ("Market Cap (mn)",          round(self.market["share_price"] * self.market["shares_outstanding"], 1), "Derived"),
        ]
        for label, val, src in drivers:
            ws.cell(row=r, column=2, value=label).font = FONT_LABEL
            c = ws.cell(row=r, column=3, value=val)
            c.font = FONT_VALUE_B
            if isinstance(val, float):
                c.number_format = FMT_MONEY2 if "Price" in label else FMT_NUM1
            ws.cell(row=r, column=4, value=src).font = FONT_SMALL
            r += 1

        r += 1
        write_subheader(ws, r, 2, 4, "CAPM / WACC Inputs"); r += 1
        capm = [
            ("10-Year Treasury Yield",  self.macro["risk_free_rate"],     FMT_PCT2, "FRED"),
            ("Market Risk Premium (US)", self.macro["market_risk_premium"],FMT_PCT2, "Damodaran"),
            ("Company Beta (levered)",  self.market["beta"],              FMT_DEC2, "Yahoo Finance"),
            ("Cost of Equity (Ke)",     self.proj["Base"]["ke"],          FMT_PCT2, "= Rf + β × MRP"),
            ("Cost of Debt (implied)",  self.derived["cost_of_debt"],     FMT_PCT2, "Interest Exp / Avg Debt"),
            ("Effective Tax Rate",      self.derived["effective_tax_rate"],FMT_PCT2, "3yr avg from 10-K"),
            ("Expected Inflation",      self.macro["expected_inflation"], FMT_PCT2, "FRED 10Y Breakeven"),
        ]
        for label, val, fmt, src in capm:
            ws.cell(row=r, column=2, value=label).font = FONT_LABEL
            c = ws.cell(row=r, column=3, value=val)
            c.font = FONT_VALUE_B
            c.number_format = fmt
            ws.cell(row=r, column=4, value=src).font = FONT_SMALL
            r += 1

        r += 1
        write_subheader(ws, r, 2, 4, "Scenario Selection"); r += 1
        ws.cell(row=r, column=2, value="Selected Case (1=Best, 2=Base, 3=Worst)").font = FONT_LABEL_B
        c = ws.cell(row=r, column=3, value=2)
        c.font = FONT_VALUE_B
        c.fill = FILL_INPUT
        add_comment(c, "Change this to 1 (Best), 2 (Base), or 3 (Worst) to switch scenario.")
        r += 2

        # WACC summary per scenario
        write_subheader(ws, r, 2, 4, "WACC & TGR by Scenario"); r += 1
        for sc in SCENARIO_NAMES:
            p = self.proj[sc]
            ws.cell(row=r, column=2, value=f"{sc} Case").font = FONT_LABEL_B
            ws.cell(row=r, column=3, value=p["wacc"]).font = FONT_VALUE
            ws.cell(row=r, column=3).number_format = FMT_PCT2
            ws.cell(row=r, column=4, value=f"TGR = {p['tgr']:.2%}").font = FONT_SMALL
            add_comment(ws.cell(row=r, column=3), RATIONALE.get(f"wacc_{sc.lower()}", ""))
            r += 1

    def _build_pl_input(self):
        """P&L Input — 5yr historical income statement."""
        ws = self.wb.create_sheet("P&L Input")
        ws.sheet_properties.tabColor = "4472C4"
        col1 = 1; val_start = 2
        set_col_widths(ws, {1: 35})
        for i in range(NH):
            ws.column_dimensions[get_column_letter(val_start + i)].width = 14

        r = 1
        write_section_header(ws, r, col1, val_start + NH - 1,
                             "Income Statement — Historical (USD mn)"); r += 1
        write_year_headers(ws, r, HIST_YEARS, val_start); r += 1

        fin = self.fin
        lines = [
            ("Revenue",              "total_revenue",        FMT_NUM, True),
            ("  Products Revenue",   "products_revenue",     FMT_NUM, False),
            ("  Services Revenue",   "services_revenue",     FMT_NUM, False),
            ("",                     None,                   None,    False),
            ("Cost of Goods Sold",   "total_cogs",           FMT_NUM, False),
            ("  Products COGS",      "products_cogs",        FMT_NUM, False),
            ("  Services COGS",      "services_cogs",        FMT_NUM, False),
            ("Gross Profit",         "gross_profit",         FMT_NUM, True),
            ("",                     None,                   None,    False),
            ("R&D Expense",          "rd_expense",           FMT_NUM, False),
            ("SG&A Expense",         "sga_expense",          FMT_NUM, False),
            ("Total Operating Expenses","total_opex",        FMT_NUM, True),
            ("Operating Income (EBIT)","operating_income",   FMT_NUM, True),
            ("",                     None,                   None,    False),
            ("Other Income/(Expense)","other_income_expense",FMT_NUM, False),
            ("Pretax Income",        "pretax_income",        FMT_NUM, True),
            ("Tax Provision",        "tax_provision",        FMT_NUM, False),
            ("Net Income",           "net_income",           FMT_NUM, True),
        ]

        for label, key, fmt, is_total in lines:
            if key is None:
                r += 1
                continue
            vals = fin.get(key, HIST_INCOME.get(key, [0]*NH))
            # Ensure we have exactly NH values
            vals = (vals + [None]*NH)[:NH]
            write_row_data(ws, r, label, vals, col1, val_start, val_fmt=fmt, is_total=is_total)
            r += 1

        # KPIs
        r += 1
        write_subheader(ws, r, col1, val_start + NH - 1, "Key Performance Indicators"); r += 1

        rev  = fin.get("total_revenue", HIST_INCOME["total_revenue"])
        gp   = fin.get("gross_profit",  HIST_INCOME["gross_profit"])
        oi   = fin.get("operating_income", HIST_INCOME["operating_income"])
        ni   = fin.get("net_income",     HIST_INCOME["net_income"])

        # Revenue Y-o-Y
        rev_growth = [None] + [round((rev[i] - rev[i-1]) / rev[i-1], 4) if rev[i-1] else None
                               for i in range(1, NH)]
        write_row_data(ws, r, "Revenue Growth %", rev_growth, col1, val_start,
                       val_fmt=FMT_PCT, label_font=FONT_KPI); r += 1

        # GP%
        gp_pct = [round(gp[i] / rev[i], 4) if rev[i] else None for i in range(NH)]
        write_row_data(ws, r, "Gross Profit %", gp_pct, col1, val_start,
                       val_fmt=FMT_PCT, label_font=FONT_KPI); r += 1

        # Products GP%
        prod_gp = self.derived.get("products_gp_pct", [])
        if prod_gp:
            write_row_data(ws, r, "Products GP%", prod_gp, col1, val_start,
                           val_fmt=FMT_PCT, label_font=FONT_KPI); r += 1

        # Services GP%
        serv_gp = self.derived.get("services_gp_pct", [])
        if serv_gp:
            write_row_data(ws, r, "Services GP%", serv_gp, col1, val_start,
                           val_fmt=FMT_PCT, label_font=FONT_KPI); r += 1

        # EBIT%
        ebit_pct = [round(oi[i] / rev[i], 4) if rev[i] else None for i in range(NH)]
        write_row_data(ws, r, "EBIT Margin %", ebit_pct, col1, val_start,
                       val_fmt=FMT_PCT, label_font=FONT_KPI); r += 1

        # Net margin
        ni_pct = [round(ni[i] / rev[i], 4) if rev[i] else None for i in range(NH)]
        write_row_data(ws, r, "Net Income %", ni_pct, col1, val_start,
                       val_fmt=FMT_PCT, label_font=FONT_KPI); r += 1

        # Segment Revenue
        r += 1
        write_subheader(ws, r, col1, val_start + NH - 1, "Segment Revenue Breakdown"); r += 1
        for seg_name in ["iPhone", "Mac", "iPad", "Wearables", "Services"]:
            vals = self.seg.get(seg_name, HIST_SEGMENTS[seg_name])
            vals = (vals + [None]*NH)[:NH]
            write_row_data(ws, r, f"  {seg_name}", vals, col1, val_start, val_fmt=FMT_NUM); r += 1

    def _build_bs_input(self):
        """Balance Sheet Input — 5yr historical."""
        ws = self.wb.create_sheet("Balance Sheet Input")
        ws.sheet_properties.tabColor = "4472C4"
        col1 = 1; val_start = 2
        set_col_widths(ws, {1: 35})
        for i in range(NH):
            ws.column_dimensions[get_column_letter(val_start + i)].width = 14

        r = 1
        write_section_header(ws, r, col1, val_start + NH - 1,
                             "Balance Sheet — Historical (USD mn)"); r += 1
        write_year_headers(ws, r, HIST_YEARS, val_start); r += 1

        bs = {**HIST_BALANCE}  # use hardcoded (most complete)

        lines = [
            ("ASSETS", None, True),
            ("Cash & Equivalents",        "cash_and_equivalents",       False),
            ("Short-Term Investments",    "short_term_investments",     False),
            ("Accounts Receivable",       "accounts_receivable",        False),
            ("Inventory",                 "inventory",                  False),
            ("Other Current Assets",      "other_current_assets",       False),
            ("Total Current Assets",      "total_current_assets",       True),
            ("",                          None,                         False),
            ("PP&E, Net",                 "ppe_net",                    False),
            ("Other Non-Current Assets",  "other_non_current_assets",   False),
            ("Total Assets",              "total_assets",               True),
            ("",                          None,                         False),
            ("LIABILITIES", None, True),
            ("Accounts Payable",          "accounts_payable",           False),
            ("Short-Term Debt",           "short_term_debt",            False),
            ("Other Current Liabilities", "other_current_liabilities",  False),
            ("Total Current Liabilities", "total_current_liabilities",  True),
            ("",                          None,                         False),
            ("Long-Term Debt",            "long_term_debt",             False),
            ("Other Non-Current Liab.",   "other_non_current_liabilities",False),
            ("Total Liabilities",         "total_liabilities",          True),
            ("",                          None,                         False),
            ("EQUITY", None, True),
            ("Stockholders' Equity",      "stockholders_equity",        True),
            ("",                          None,                         False),
            ("Total L + E",               None,                         True),
        ]

        for label, key, is_total in lines:
            if key is None and label == "":
                r += 1; continue
            if key is None and label in ("ASSETS", "LIABILITIES", "EQUITY"):
                write_subheader(ws, r, col1, val_start + NH - 1, label); r += 1; continue
            if label == "Total L + E":
                total_le = [bs["total_liabilities"][i] + bs["stockholders_equity"][i]
                            for i in range(NH)]
                write_row_data(ws, r, label, total_le, col1, val_start, val_fmt=FMT_NUM, is_total=True)
                r += 1; continue
            vals = bs.get(key, [0]*NH)
            vals = (vals + [None]*NH)[:NH]
            write_row_data(ws, r, label, vals, col1, val_start, val_fmt=FMT_NUM, is_total=is_total)
            r += 1

        # Balance check
        r += 1
        ws.cell(row=r, column=col1, value="Balance Check (Assets - L&E)").font = FONT_KPI
        for i in range(NH):
            ta  = bs["total_assets"][i]
            tle = bs["total_liabilities"][i] + bs["stockholders_equity"][i]
            diff = round(ta - tle, 1)
            c = ws.cell(row=r, column=val_start + i, value=diff)
            c.font = FONT_CHECK_OK if abs(diff) < 1 else FONT_WARNING
            c.number_format = FMT_NUM1

        # KPIs
        r += 2
        write_subheader(ws, r, col1, val_start + NH - 1, "Balance Sheet KPIs"); r += 1

        ta = bs["total_assets"]
        eq = bs["stockholders_equity"]
        ni = HIST_INCOME["net_income"]
        roa = [round(ni[i] / ta[i], 4) if ta[i] else None for i in range(NH)]
        roe = [round(ni[i] / eq[i], 4) if eq[i] else None for i in range(NH)]
        write_row_data(ws, r, "ROA", roa, col1, val_start, val_fmt=FMT_PCT, label_font=FONT_KPI); r += 1
        write_row_data(ws, r, "ROE", roe, col1, val_start, val_fmt=FMT_PCT, label_font=FONT_KPI); r += 1

    def _build_segment_tab(self, seg_name: str):
        """Build segment tab for iPhone/Mac/iPad/Wearables."""
        ws = self.wb.create_sheet(f"Segment - {seg_name}")
        ws.sheet_properties.tabColor = "70AD47"
        col1 = 1; val_start = 2
        set_col_widths(ws, {1: 35})

        r = 1
        total_cols = NH + NP * 3  # hist + 3 scenarios × 10 years
        write_section_header(ws, r, col1, val_start + total_cols - 1,
                             f"Segment — {seg_name}"); r += 1

        # Year headers: historical + 3 scenario blocks
        for i, yr in enumerate(HIST_YEARS):
            c = ws.cell(row=r, column=val_start + i, value=f"FY{yr}")
            c.font = FONT_HEADER; c.fill = FILL_HEADER
            c.alignment = ALIGN_CENTER; c.border = BORDER_THIN

        proj_start = val_start + NH
        write_scenario_headers(ws, r, proj_start, NP); r += 1

        # Sub-year headers for forecast
        for si in range(3):
            for j, yr in enumerate(PROJ_YEARS):
                col = proj_start + si * NP + j
                c = ws.cell(row=r, column=col, value=f"FY{yr}")
                c.font = FONT_SMALL; c.alignment = ALIGN_CENTER; c.border = BORDER_THIN
        r += 1

        hist_rev = self.seg.get(seg_name, HIST_SEGMENTS[seg_name])

        # ── Revenue ──
        write_subheader(ws, r, col1, val_start + total_cols - 1, "Revenue"); r += 1

        # Historical revenue
        ws.cell(row=r, column=col1, value=f"{seg_name} Revenue").font = FONT_LABEL_B
        for i, v in enumerate(hist_rev):
            c = ws.cell(row=r, column=val_start + i, value=v)
            c.number_format = FMT_NUM; c.font = FONT_VALUE
        # Projected revenue (3 scenarios)
        for si, sc in enumerate(SCENARIO_NAMES):
            vals = self.proj[sc]["seg_rev"][seg_name]
            for j, v in enumerate(vals):
                c = ws.cell(row=r, column=proj_start + si * NP + j, value=v)
                c.number_format = FMT_NUM; c.font = FONT_VALUE
        r += 1

        # Y-o-Y Growth
        ws.cell(row=r, column=col1, value="Y-o-Y Growth %").font = FONT_KPI
        # Historical growth
        for i in range(1, NH):
            if hist_rev[i-1] > 0:
                g = (hist_rev[i] - hist_rev[i-1]) / hist_rev[i-1]
                c = ws.cell(row=r, column=val_start + i, value=round(g, 4))
                c.number_format = FMT_PCT; c.font = FONT_KPI
        # Projected growth
        growth_key = f"{seg_name}_growth"
        for si, sc in enumerate(SCENARIO_NAMES):
            growth = SCENARIOS.get(growth_key, {}).get(sc, [0.02]*NP)
            for j, g in enumerate(growth):
                c = ws.cell(row=r, column=proj_start + si * NP + j, value=g)
                c.number_format = FMT_PCT; c.font = FONT_KPI
                add_comment(c, RATIONALE.get(f"{seg_name}_growth_{sc.lower()}", ""))
        r += 2

        # ── Gross Profit ──
        write_subheader(ws, r, col1, val_start + total_cols - 1, "Gross Profit"); r += 1

        # Historical GP% (use blended products GP%)
        prod_gp_hist = self.derived.get("products_gp_pct", [0.32]*NH)
        diff = SEGMENT_GP_DIFF.get(seg_name, 0)

        ws.cell(row=r, column=col1, value="Blended Products GP%").font = FONT_LABEL
        for i, gp in enumerate(prod_gp_hist):
            c = ws.cell(row=r, column=val_start + i, value=round(gp, 4))
            c.number_format = FMT_PCT; c.font = FONT_VALUE
        r += 1

        ws.cell(row=r, column=col1, value=f"Segment Differential").font = FONT_LABEL
        c = ws.cell(row=r, column=val_start, value=diff)
        c.number_format = FMT_PCT; c.font = FONT_VALUE_B
        add_comment(c, SEGMENT_COMPARABLES.get(seg_name, ""))
        r += 1

        ws.cell(row=r, column=col1, value=f"{seg_name} GP%").font = FONT_LABEL_B
        for i, gp in enumerate(prod_gp_hist):
            c = ws.cell(row=r, column=val_start + i, value=round(gp + diff, 4))
            c.number_format = FMT_PCT; c.font = FONT_VALUE_B
        for si, sc in enumerate(SCENARIO_NAMES):
            gp_pct = self.proj[sc]["seg_gp"][seg_name]["gp_pct"]
            for j in range(NP):
                c = ws.cell(row=r, column=proj_start + si * NP + j, value=round(gp_pct, 4))
                c.number_format = FMT_PCT; c.font = FONT_VALUE_B
        r += 1

        ws.cell(row=r, column=col1, value=f"{seg_name} Gross Profit").font = FONT_LABEL_B
        for i in range(NH):
            gp_val = round(hist_rev[i] * (prod_gp_hist[i] + diff), 1)
            c = ws.cell(row=r, column=val_start + i, value=gp_val)
            c.number_format = FMT_NUM; c.font = FONT_VALUE_B
        for si, sc in enumerate(SCENARIO_NAMES):
            gp_vals = self.proj[sc]["seg_gp"][seg_name]["gp"]
            for j, v in enumerate(gp_vals):
                c = ws.cell(row=r, column=proj_start + si * NP + j, value=v)
                c.number_format = FMT_NUM; c.font = FONT_VALUE_B
        r += 2

        # Comparables
        write_subheader(ws, r, col1, val_start + 4, "Comparable Companies (GP% Rationale)"); r += 1
        ws.cell(row=r, column=col1, value="Source / Rationale").font = FONT_SMALL
        ws.cell(row=r, column=val_start, value=SEGMENT_COMPARABLES.get(seg_name, "")).font = FONT_SMALL

    def _build_services_tab(self):
        """Segment - Services."""
        ws = self.wb.create_sheet("Segment - Services")
        ws.sheet_properties.tabColor = "70AD47"
        col1 = 1; val_start = 2
        set_col_widths(ws, {1: 35})

        r = 1
        total_cols = NH + NP * 3
        write_section_header(ws, r, col1, val_start + total_cols - 1,
                             "Segment — Services"); r += 1

        # Year headers
        for i, yr in enumerate(HIST_YEARS):
            c = ws.cell(row=r, column=val_start + i, value=f"FY{yr}")
            c.font = FONT_HEADER; c.fill = FILL_HEADER
            c.alignment = ALIGN_CENTER
        proj_start = val_start + NH
        write_scenario_headers(ws, r, proj_start, NP); r += 1
        for si in range(3):
            for j, yr in enumerate(PROJ_YEARS):
                col = proj_start + si * NP + j
                c = ws.cell(row=r, column=col, value=f"FY{yr}")
                c.font = FONT_SMALL; c.alignment = ALIGN_CENTER
        r += 1

        hist = self.seg.get("Services", HIST_SEGMENTS["Services"])

        # Revenue
        write_subheader(ws, r, col1, val_start + total_cols - 1, "Revenue"); r += 1
        ws.cell(row=r, column=col1, value="Services Revenue").font = FONT_LABEL_B
        for i, v in enumerate(hist):
            ws.cell(row=r, column=val_start + i, value=v).number_format = FMT_NUM
        for si, sc in enumerate(SCENARIO_NAMES):
            for j, v in enumerate(self.proj[sc]["seg_rev"]["Services"]):
                ws.cell(row=r, column=proj_start + si * NP + j, value=v).number_format = FMT_NUM
        r += 1

        # Growth
        ws.cell(row=r, column=col1, value="Y-o-Y Growth %").font = FONT_KPI
        for i in range(1, NH):
            if hist[i-1] > 0:
                ws.cell(row=r, column=val_start + i,
                        value=round((hist[i]-hist[i-1])/hist[i-1], 4)).number_format = FMT_PCT
        for si, sc in enumerate(SCENARIO_NAMES):
            for j, g in enumerate(SCENARIOS["Services_growth"][sc]):
                c = ws.cell(row=r, column=proj_start + si * NP + j, value=g)
                c.number_format = FMT_PCT
                add_comment(c, RATIONALE.get(f"Services_growth_{sc.lower()}", ""))
        r += 2

        # GP%
        write_subheader(ws, r, col1, val_start + total_cols - 1, "Gross Profit"); r += 1
        serv_gp_hist = self.derived.get("services_gp_pct", [0.66]*NH)
        ws.cell(row=r, column=col1, value="Services GP%").font = FONT_LABEL_B
        for i, gp in enumerate(serv_gp_hist):
            ws.cell(row=r, column=val_start + i, value=round(gp, 4)).number_format = FMT_PCT
        for si, sc in enumerate(SCENARIO_NAMES):
            gp = SCENARIOS["services_gp_pct"][sc]
            for j in range(NP):
                c = ws.cell(row=r, column=proj_start + si * NP + j, value=gp)
                c.number_format = FMT_PCT
                add_comment(c, RATIONALE.get(f"services_gp_{sc.lower()}", ""))
        r += 1

        ws.cell(row=r, column=col1, value="Services Gross Profit").font = FONT_LABEL_B
        for i in range(NH):
            ws.cell(row=r, column=val_start + i,
                    value=round(hist[i] * serv_gp_hist[i], 1)).number_format = FMT_NUM
        for si, sc in enumerate(SCENARIO_NAMES):
            for j, v in enumerate(self.proj[sc]["seg_gp"]["Services"]["gp"]):
                ws.cell(row=r, column=proj_start + si * NP + j, value=v).number_format = FMT_NUM

    def _build_revenue_gp_summary(self):
        """Revenue & GP Summary — aggregates all segments."""
        ws = self.wb.create_sheet("Revenue & GP Summary")
        ws.sheet_properties.tabColor = "70AD47"
        col1 = 1; val_start = 2
        set_col_widths(ws, {1: 35})

        r = 1
        total_cols = NH + NP * 3
        write_section_header(ws, r, col1, val_start + total_cols - 1,
                             "Revenue & Gross Profit Summary"); r += 1

        for i, yr in enumerate(HIST_YEARS):
            c = ws.cell(row=r, column=val_start + i, value=f"FY{yr}")
            c.font = FONT_HEADER; c.fill = FILL_HEADER; c.alignment = ALIGN_CENTER
        proj_start = val_start + NH
        write_scenario_headers(ws, r, proj_start, NP); r += 1
        for si in range(3):
            for j, yr in enumerate(PROJ_YEARS):
                ws.cell(row=r, column=proj_start + si * NP + j,
                        value=f"FY{yr}").font = FONT_SMALL
        r += 1

        # Revenue by segment
        write_subheader(ws, r, col1, val_start + total_cols - 1, "Revenue by Segment"); r += 1
        for seg in ["iPhone", "Mac", "iPad", "Wearables", "Services"]:
            ws.cell(row=r, column=col1, value=seg).font = FONT_LABEL
            hist = self.seg.get(seg, HIST_SEGMENTS[seg])
            for i, v in enumerate(hist):
                ws.cell(row=r, column=val_start + i, value=v).number_format = FMT_NUM
            for si, sc in enumerate(SCENARIO_NAMES):
                for j, v in enumerate(self.proj[sc]["seg_rev"][seg]):
                    ws.cell(row=r, column=proj_start + si * NP + j, value=v).number_format = FMT_NUM
            r += 1

        # Total Revenue
        ws.cell(row=r, column=col1, value="Total Revenue").font = FONT_LABEL_B
        hist_total = HIST_INCOME["total_revenue"]
        for i, v in enumerate(hist_total):
            c = ws.cell(row=r, column=val_start + i, value=v)
            c.number_format = FMT_NUM; c.font = FONT_VALUE_B; c.border = BORDER_TOP
        for si, sc in enumerate(SCENARIO_NAMES):
            for j, v in enumerate(self.proj[sc]["total_rev"]):
                c = ws.cell(row=r, column=proj_start + si * NP + j, value=round(v, 1))
                c.number_format = FMT_NUM; c.font = FONT_VALUE_B; c.border = BORDER_TOP
        r += 2

        # Gross Profit summary
        write_subheader(ws, r, col1, val_start + total_cols - 1, "Gross Profit"); r += 1
        ws.cell(row=r, column=col1, value="Total Gross Profit").font = FONT_LABEL_B
        hist_gp = HIST_INCOME["gross_profit"]
        for i, v in enumerate(hist_gp):
            ws.cell(row=r, column=val_start + i, value=v).number_format = FMT_NUM
        for si, sc in enumerate(SCENARIO_NAMES):
            for j, v in enumerate(self.proj[sc]["gross_profit"]):
                ws.cell(row=r, column=proj_start + si * NP + j, value=round(v, 1)).number_format = FMT_NUM
        r += 1

        # Overall GP%
        ws.cell(row=r, column=col1, value="Overall GP%").font = FONT_KPI
        for i in range(NH):
            ws.cell(row=r, column=val_start + i,
                    value=round(hist_gp[i] / hist_total[i], 4)).number_format = FMT_PCT
        for si, sc in enumerate(SCENARIO_NAMES):
            for j, v in enumerate(self.proj[sc]["overall_gp_pct"]):
                ws.cell(row=r, column=proj_start + si * NP + j, value=round(v, 4)).number_format = FMT_PCT

    def _build_opex(self):
        ws = self.wb.create_sheet("Opex")
        ws.sheet_properties.tabColor = "70AD47"
        col1 = 1; val_start = 2
        set_col_widths(ws, {1: 35})

        r = 1
        total_cols = NH + NP * 3
        write_section_header(ws, r, col1, val_start + total_cols - 1,
                             "Operating Expenses"); r += 1

        for i, yr in enumerate(HIST_YEARS):
            ws.cell(row=r, column=val_start + i, value=f"FY{yr}").font = FONT_HEADER
            ws.cell(row=r, column=val_start + i).fill = FILL_HEADER
        proj_start = val_start + NH
        write_scenario_headers(ws, r, proj_start, NP); r += 1
        for si in range(3):
            for j, yr in enumerate(PROJ_YEARS):
                ws.cell(row=r, column=proj_start + si * NP + j, value=f"FY{yr}").font = FONT_SMALL
        r += 1

        rev_hist = HIST_INCOME["total_revenue"]

        for label, key, sc_key in [("R&D Expense", "rd_expense", "rd_pct_rev"),
                                    ("SG&A Expense", "sga_expense", "sga_pct_rev")]:
            ws.cell(row=r, column=col1, value=label).font = FONT_LABEL_B
            hist = HIST_INCOME[key]
            for i, v in enumerate(hist):
                ws.cell(row=r, column=val_start + i, value=v).number_format = FMT_NUM
            for si, sc in enumerate(SCENARIO_NAMES):
                for j, v in enumerate(self.proj[sc][key]):
                    ws.cell(row=r, column=proj_start + si * NP + j, value=v).number_format = FMT_NUM
            r += 1

            # As % of revenue
            ws.cell(row=r, column=col1, value=f"  as % of Revenue").font = FONT_KPI
            for i in range(NH):
                ws.cell(row=r, column=val_start + i,
                        value=round(hist[i] / rev_hist[i], 4)).number_format = FMT_PCT
            for si, sc in enumerate(SCENARIO_NAMES):
                pct = SCENARIOS[sc_key][sc]
                for j in range(NP):
                    ws.cell(row=r, column=proj_start + si * NP + j, value=pct).number_format = FMT_PCT
            r += 2

    def _build_ppe(self):
        ws = self.wb.create_sheet("PP&E")
        ws.sheet_properties.tabColor = "70AD47"
        col1 = 1; val_start = 2
        set_col_widths(ws, {1: 35})

        r = 1
        total_cols = NH + NP * 3
        write_section_header(ws, r, col1, val_start + total_cols - 1,
                             "PP&E Roll-Forward"); r += 1
        for i, yr in enumerate(HIST_YEARS):
            ws.cell(row=r, column=val_start + i, value=f"FY{yr}").font = FONT_HEADER
            ws.cell(row=r, column=val_start + i).fill = FILL_HEADER
        proj_start = val_start + NH
        write_scenario_headers(ws, r, proj_start, NP); r += 1
        for si in range(3):
            for j, yr in enumerate(PROJ_YEARS):
                ws.cell(row=r, column=proj_start + si * NP + j, value=f"FY{yr}").font = FONT_SMALL
        r += 1

        for label, key in [("PP&E, Net", "ppe_net"), ("Depreciation", "depreciation"),
                            ("CapEx", "capex")]:
            ws.cell(row=r, column=col1, value=label).font = FONT_LABEL_B
            h_source = HIST_BALANCE if key == "ppe_net" else HIST_OTHER
            for i, v in enumerate(h_source.get(key, [0]*NH)):
                ws.cell(row=r, column=val_start + i, value=v).number_format = FMT_NUM
            for si, sc in enumerate(SCENARIO_NAMES):
                for j, v in enumerate(self.proj[sc][key]):
                    ws.cell(row=r, column=proj_start + si * NP + j, value=v).number_format = FMT_NUM
            r += 1

    def _build_working_capital(self):
        ws = self.wb.create_sheet("Working Capital")
        ws.sheet_properties.tabColor = "70AD47"
        col1 = 1; val_start = 2
        set_col_widths(ws, {1: 35})

        r = 1
        total_cols = NH + NP * 3
        write_section_header(ws, r, col1, val_start + total_cols - 1,
                             "Working Capital Schedule"); r += 1
        for i, yr in enumerate(HIST_YEARS):
            ws.cell(row=r, column=val_start + i, value=f"FY{yr}").font = FONT_HEADER
            ws.cell(row=r, column=val_start + i).fill = FILL_HEADER
        proj_start = val_start + NH
        write_scenario_headers(ws, r, proj_start, NP); r += 1
        for si in range(3):
            for j, yr in enumerate(PROJ_YEARS):
                ws.cell(row=r, column=proj_start + si * NP + j, value=f"FY{yr}").font = FONT_SMALL
        r += 1

        # DSO/DIO/DPO
        for label, key, hist_key in [
            ("DSO (days)", "dso", "dso"),
            ("DIO (days)", "dio", "dio"),
            ("DPO (days)", "dpo", "dpo"),
        ]:
            ws.cell(row=r, column=col1, value=label).font = FONT_LABEL_B
            hist = self.derived.get(hist_key, [0]*NH)
            for i, v in enumerate(hist):
                ws.cell(row=r, column=val_start + i, value=v).number_format = FMT_DAYS
            for si, sc in enumerate(SCENARIO_NAMES):
                days_val = WC_ASSUMPTIONS[hist_key][sc]
                for j in range(NP):
                    ws.cell(row=r, column=proj_start + si * NP + j, value=days_val).number_format = FMT_DAYS
            r += 1

        r += 1
        # NWC components
        for label, key in [("Accounts Receivable", "accounts_receivable"),
                            ("Inventory", "inventory"),
                            ("Accounts Payable", "accounts_payable")]:
            ws.cell(row=r, column=col1, value=label).font = FONT_LABEL
            hist_bs = HIST_BALANCE[key]
            for i, v in enumerate(hist_bs):
                ws.cell(row=r, column=val_start + i, value=v).number_format = FMT_NUM
            for si, sc in enumerate(SCENARIO_NAMES):
                for j, v in enumerate(self.proj[sc][key]):
                    ws.cell(row=r, column=proj_start + si * NP + j, value=v).number_format = FMT_NUM
            r += 1

        # NWC and delta NWC
        r += 1
        ws.cell(row=r, column=col1, value="Net Working Capital").font = FONT_LABEL_B
        for i in range(NH):
            nwc = HIST_BALANCE["accounts_receivable"][i] + HIST_BALANCE["inventory"][i] - HIST_BALANCE["accounts_payable"][i]
            ws.cell(row=r, column=val_start + i, value=round(nwc, 1)).number_format = FMT_NUM
        for si, sc in enumerate(SCENARIO_NAMES):
            for j, v in enumerate(self.proj[sc]["nwc"]):
                ws.cell(row=r, column=proj_start + si * NP + j, value=round(v, 1)).number_format = FMT_NUM
        r += 1

        ws.cell(row=r, column=col1, value="Δ NWC").font = FONT_LABEL_B
        for si, sc in enumerate(SCENARIO_NAMES):
            for j, v in enumerate(self.proj[sc]["delta_nwc"]):
                ws.cell(row=r, column=proj_start + si * NP + j, value=round(v, 1)).number_format = FMT_NUM

    def _build_financing_wacc(self):
        ws = self.wb.create_sheet("Financing & WACC")
        ws.sheet_properties.tabColor = "70AD47"
        col1 = 1
        set_col_widths(ws, {1: 35, 2: 15, 3: 15, 4: 15, 5: 30})

        r = 1
        write_section_header(ws, r, col1, 5, "Financing & WACC"); r += 2

        ws.cell(row=r, column=2, value="Best").font = FONT_SUBHEADER
        ws.cell(row=r, column=3, value="Base").font = FONT_SUBHEADER
        ws.cell(row=r, column=4, value="Worst").font = FONT_SUBHEADER
        ws.cell(row=r, column=5, value="Source").font = FONT_SUBHEADER
        r += 1

        rows = [
            ("Risk-Free Rate", [self.macro["risk_free_rate"]]*3, FMT_PCT2, "FRED 10Y UST"),
            ("Beta", [self.market["beta"]]*3, FMT_DEC2, "Yahoo Finance"),
            ("Market Risk Premium", [self.macro["market_risk_premium"]]*3, FMT_PCT2, "Damodaran"),
            ("Cost of Equity (Ke)", [self.proj[s]["ke"] for s in SCENARIO_NAMES], FMT_PCT2, "CAPM: Rf + β×MRP"),
            ("Cost of Debt (Kd)", [self.derived["cost_of_debt"]]*3, FMT_PCT2, "Implied from 10-K"),
            ("Effective Tax Rate", [self.derived["effective_tax_rate"]]*3, FMT_PCT2, "3yr avg"),
            ("After-Tax Kd", [self.derived["cost_of_debt"] * (1-self.derived["effective_tax_rate"])]*3,
             FMT_PCT2, "Kd × (1-t)"),
            ("Equity Weight (We)", [self.proj[s]["we"] for s in SCENARIO_NAMES], FMT_PCT2, "Mkt cap / (Mkt cap + Debt)"),
            ("Debt Weight (Wd)", [self.proj[s]["wd"] for s in SCENARIO_NAMES], FMT_PCT2, "Debt / (Mkt cap + Debt)"),
            ("", None, None, ""),
            ("WACC", [self.proj[s]["wacc"] for s in SCENARIO_NAMES], FMT_PCT2, "We×Ke + Wd×Kd×(1-t)"),
            ("Terminal Growth Rate", [self.proj[s]["tgr"] for s in SCENARIO_NAMES], FMT_PCT2, "Linked to inflation"),
            ("WACC - g Spread", [self.proj[s]["wacc"] - self.proj[s]["tgr"] for s in SCENARIO_NAMES],
             FMT_PCT2, "Must be > 0"),
        ]

        for label, vals, fmt, src in rows:
            if vals is None:
                r += 1; continue
            ws.cell(row=r, column=col1, value=label).font = FONT_LABEL_B if "WACC" in label else FONT_LABEL
            for si, v in enumerate(vals):
                c = ws.cell(row=r, column=2 + si, value=v)
                c.number_format = fmt
                c.font = FONT_VALUE_B if "WACC" == label else FONT_VALUE
                if "WACC - g" in label and v < 0.02:
                    c.font = FONT_WARNING
                    c.fill = FILL_WARNING
            ws.cell(row=r, column=5, value=src).font = FONT_SMALL
            r += 1

    def _build_pl_output(self):
        """Projected P&L (10yr × 3 scenarios)."""
        ws = self.wb.create_sheet("P&L")
        ws.sheet_properties.tabColor = "ED7D31"
        col1 = 1; val_start = 2
        set_col_widths(ws, {1: 35})

        r = 1
        total_cols = NP * 3
        write_section_header(ws, r, col1, val_start + total_cols - 1,
                             "Projected Income Statement (USD mn)"); r += 1
        proj_start = val_start
        write_scenario_headers(ws, r, proj_start, NP); r += 1
        for si in range(3):
            for j, yr in enumerate(PROJ_YEARS):
                ws.cell(row=r, column=proj_start + si * NP + j, value=f"FY{yr}").font = FONT_SMALL
        r += 1

        lines = [
            ("Products Revenue",    "products_rev",    False),
            ("Services Revenue",    "services_rev",    False),
            ("Total Revenue",       "total_rev",       True),
            ("Products COGS",       "products_cogs",   False),
            ("Services COGS",       "services_cogs",   False),
            ("Total COGS",          "total_cogs",      False),
            ("Gross Profit",        "gross_profit",    True),
            ("R&D Expense",         "rd_expense",      False),
            ("SG&A Expense",        "sga_expense",     False),
            ("Total OpEx",          "total_opex",      False),
            ("Operating Income",    "operating_income",True),
            ("Other Income/(Exp)",  "other_income",    False),
            ("Pretax Income",       "pretax_income",   True),
            ("Tax Provision",       "tax_provision",   False),
            ("Net Income",          "net_income",      True),
        ]

        for label, key, is_total in lines:
            ws.cell(row=r, column=col1, value=label).font = FONT_LABEL_B if is_total else FONT_LABEL
            for si, sc in enumerate(SCENARIO_NAMES):
                vals = self.proj[sc][key]
                for j, v in enumerate(vals):
                    c = ws.cell(row=r, column=proj_start + si * NP + j, value=round(v, 1))
                    c.number_format = FMT_NUM
                    c.font = FONT_VALUE_B if is_total else FONT_VALUE
                    if is_total:
                        c.border = BORDER_TOP
            r += 1

    def _build_bs_output(self):
        """Projected Balance Sheet."""
        ws = self.wb.create_sheet("Balance Sheet")
        ws.sheet_properties.tabColor = "ED7D31"
        col1 = 1; val_start = 2
        set_col_widths(ws, {1: 35})

        r = 1
        write_section_header(ws, r, col1, val_start + NP * 3 - 1,
                             "Projected Balance Sheet (USD mn)"); r += 1
        write_scenario_headers(ws, r, val_start, NP); r += 1
        for si in range(3):
            for j, yr in enumerate(PROJ_YEARS):
                ws.cell(row=r, column=val_start + si * NP + j, value=f"FY{yr}").font = FONT_SMALL
        r += 1

        for label, key, is_total in [
            ("PP&E, Net",               "ppe_net",                  False),
            ("Total Assets",            "total_assets",             True),
            ("Total Liabilities",       "total_liabilities",        True),
            ("Stockholders' Equity",    "stockholders_equity",      True),
        ]:
            ws.cell(row=r, column=col1, value=label).font = FONT_LABEL_B if is_total else FONT_LABEL
            for si, sc in enumerate(SCENARIO_NAMES):
                for j, v in enumerate(self.proj[sc][key]):
                    c = ws.cell(row=r, column=val_start + si * NP + j, value=round(v, 1))
                    c.number_format = FMT_NUM; c.font = FONT_VALUE_B if is_total else FONT_VALUE
            r += 1

    def _build_cash_flow(self):
        """FCF Build-Up."""
        ws = self.wb.create_sheet("Cash Flow")
        ws.sheet_properties.tabColor = "ED7D31"
        col1 = 1; val_start = 2
        set_col_widths(ws, {1: 35})

        r = 1
        write_section_header(ws, r, col1, val_start + NP * 3 - 1,
                             "Unlevered Free Cash Flow Build-Up (USD mn)"); r += 1
        write_scenario_headers(ws, r, val_start, NP); r += 1
        for si in range(3):
            for j, yr in enumerate(PROJ_YEARS):
                ws.cell(row=r, column=val_start + si * NP + j, value=f"FY{yr}").font = FONT_SMALL
        r += 1

        lines = [
            ("EBIT",           "operating_income", False),
            ("× (1 − Tax Rate)","nopat",            True),
            ("+ D&A",          "depreciation",     False),
            ("− CapEx",        "capex",            False),
            ("− Δ NWC",        "delta_nwc",        False),
            ("= UFCF",         "ufcf",             True),
        ]
        for label, key, is_total in lines:
            ws.cell(row=r, column=col1, value=label).font = FONT_LABEL_B if is_total else FONT_LABEL
            for si, sc in enumerate(SCENARIO_NAMES):
                for j, v in enumerate(self.proj[sc][key]):
                    c = ws.cell(row=r, column=val_start + si * NP + j, value=round(v, 1))
                    c.number_format = FMT_NUM
                    if is_total:
                        c.font = FONT_VALUE_B; c.border = BORDER_TOP
            r += 1

    def _build_dcf(self):
        """DCF Valuation — all 3 scenarios side by side."""
        ws = self.wb.create_sheet("DCF")
        ws.sheet_properties.tabColor = "ED7D31"
        col1 = 1
        set_col_widths(ws, {1: 35, 2: 18, 3: 18, 4: 18, 5: 30})

        r = 1
        write_section_header(ws, r, col1, 5, "DCF Valuation Summary"); r += 2

        ws.cell(row=r, column=2, value="Best Case").font = FONT_SUBHEADER
        ws.cell(row=r, column=2).fill = FILL_SCENARIO_B
        ws.cell(row=r, column=3, value="Base Case").font = FONT_SUBHEADER
        ws.cell(row=r, column=3).fill = FILL_SCENARIO_M
        ws.cell(row=r, column=4, value="Worst Case").font = FONT_SUBHEADER
        ws.cell(row=r, column=4).fill = FILL_SCENARIO_W
        ws.cell(row=r, column=5, value="Notes").font = FONT_SUBHEADER
        r += 1

        # PV of FCFs (year by year)
        write_subheader(ws, r, col1, 5, "PV of Forecast FCFs"); r += 1
        for yi in range(NP):
            ws.cell(row=r, column=col1, value=f"Year {yi+1} (FY{PROJ_YEARS[yi]})").font = FONT_LABEL
            for si, sc in enumerate(SCENARIO_NAMES):
                ws.cell(row=r, column=2 + si,
                        value=round(self.proj[sc]["pv_fcf"][yi], 1)).number_format = FMT_NUM
            r += 1

        # Totals
        r += 1
        summary_rows = [
            ("Σ PV of FCFs",          "sum_pv_fcf",    FMT_NUM,   "Sum of discounted FCFs"),
            ("Terminal Value",        "tv",            FMT_NUM,   "Gordon Growth: UFCF(10)×(1+g)/(WACC−g)"),
            ("PV of Terminal Value",  "pv_tv",         FMT_NUM,   "TV discounted to present"),
            ("Enterprise Value (EV)", "ev",            FMT_NUM,   "Σ PV(FCF) + PV(TV)"),
            ("+ Cash & Securities",   "cash_bs",       FMT_NUM,   "From latest BS"),
            ("− Total Debt",          "debt_bs",       FMT_NUM,   "From latest BS"),
            ("= Equity Value",        "equity_value",  FMT_NUM,   "EV + Cash − Debt"),
            ("÷ Shares Outstanding",  None,            FMT_NUM1,  ""),
            ("= Implied Price/Share", "implied_price", FMT_MONEY2,""),
            ("TV as % of EV",         "tv_pct_ev",     FMT_PCT,   "Sanity check (typical 60-80%)"),
        ]

        for label, key, fmt, note in summary_rows:
            ws.cell(row=r, column=col1, value=label).font = FONT_LABEL_B
            for si, sc in enumerate(SCENARIO_NAMES):
                p = self.proj[sc]
                if key:
                    val = p[key]
                else:
                    val = self.market["shares_outstanding"]
                c = ws.cell(row=r, column=2 + si, value=val)
                c.number_format = fmt
                c.font = FONT_VALUE_B
                if key == "implied_price":
                    c.font = FONT_TITLE
                    c.fill = FILL_HIGHLIGHT
                if key == "tv_pct_ev" and val > 85:
                    c.fill = FILL_WARNING
                    c.font = FONT_WARNING
            ws.cell(row=r, column=5, value=note).font = FONT_SMALL
            r += 1

        # WACC - g check
        r += 2
        write_subheader(ws, r, col1, 5, "Model Stability Check"); r += 1
        ws.cell(row=r, column=col1, value="WACC − g spread").font = FONT_LABEL_B
        for si, sc in enumerate(SCENARIO_NAMES):
            spread = self.proj[sc]["wacc"] - self.proj[sc]["tgr"]
            c = ws.cell(row=r, column=2 + si, value=spread)
            c.number_format = FMT_PCT2
            if spread <= 0.02:
                c.font = FONT_WARNING; c.fill = FILL_WARNING
                add_comment(c, "⚠️ WACC − g ≤ 2%: Model is highly sensitive to small changes")
            else:
                c.font = FONT_CHECK_OK

    def _build_sensitivity(self):
        """Sensitivity tables."""
        ws = self.wb.create_sheet("Sensitivity")
        ws.sheet_properties.tabColor = "ED7D31"
        col1 = 1
        set_col_widths(ws, {1: 20})

        r = 1
        write_section_header(ws, r, col1, 15,
                             "Sensitivity Analysis — Implied Price/Share"); r += 2

        # Base Case: 2D table (WACC × TGR)
        write_subheader(ws, r, col1, 15, "Base Case — WACC vs Terminal Growth Rate"); r += 1

        base_wacc = self.proj["Base"]["wacc"]
        base_tgr  = self.proj["Base"]["tgr"]
        base_p    = self.proj["Base"]

        wacc_range = [round(base_wacc + (i - 6) * 0.0025, 4) for i in range(13)]
        tgr_range  = [round(base_tgr + (i - 4) * 0.0025, 4) for i in range(9)]

        # TGR headers
        ws.cell(row=r, column=col1, value="WACC \\ TGR").font = FONT_HEADER
        ws.cell(row=r, column=col1).fill = FILL_HEADER
        for ti, tgr in enumerate(tgr_range):
            c = ws.cell(row=r, column=2 + ti, value=tgr)
            c.number_format = FMT_PCT2; c.font = FONT_HEADER; c.fill = FILL_HEADER
            ws.column_dimensions[get_column_letter(2 + ti)].width = 12
        r += 1

        # Matrix
        for wi, wacc in enumerate(wacc_range):
            c = ws.cell(row=r, column=col1, value=wacc)
            c.number_format = FMT_PCT2; c.font = FONT_LABEL_B
            c.fill = FILL_SUBHEADER

            for ti, tgr in enumerate(tgr_range):
                if wacc <= tgr:
                    c2 = ws.cell(row=r, column=2 + ti, value="N/A")
                    c2.font = FONT_WARNING
                else:
                    # Recompute implied price
                    last_ufcf = base_p["ufcf"][-1]
                    tv = last_ufcf * (1 + tgr) / (wacc - tgr)
                    disc = [1 / (1 + wacc)**t for t in range(1, NP + 1)]
                    sum_pv = sum(base_p["ufcf"][i] * disc[i] for i in range(NP))
                    pv_tv = tv * disc[-1]
                    ev = sum_pv + pv_tv
                    eq = ev + base_p["cash_bs"] - base_p["debt_bs"]
                    price = eq / self.market["shares_outstanding"]

                    c2 = ws.cell(row=r, column=2 + ti, value=round(price, 2))
                    c2.number_format = FMT_MONEY2
                    c2.font = FONT_VALUE

                    # Highlight base case cell
                    is_base = (abs(wacc - base_wacc) < 0.001 and abs(tgr - base_tgr) < 0.001)
                    if is_base:
                        c2.fill = FILL_HIGHLIGHT
                        c2.font = FONT_VALUE_B
                        add_comment(c2, "← Base Case implied price")

            r += 1

        # 1D sensitivity for Best and Worst
        for sc in ["Best", "Worst"]:
            r += 2
            write_subheader(ws, r, col1, 10, f"{sc} Case — WACC Sensitivity"); r += 1
            sc_wacc = self.proj[sc]["wacc"]
            sc_tgr  = self.proj[sc]["tgr"]
            sc_p    = self.proj[sc]

            wacc_1d = [round(sc_wacc + (i - 4) * 0.0025, 4) for i in range(9)]
            ws.cell(row=r, column=col1, value="WACC").font = FONT_HEADER
            ws.cell(row=r, column=col1).fill = FILL_HEADER
            for wi, w in enumerate(wacc_1d):
                c = ws.cell(row=r, column=2 + wi, value=w)
                c.number_format = FMT_PCT2; c.font = FONT_HEADER; c.fill = FILL_HEADER
            r += 1

            ws.cell(row=r, column=col1, value="Price/Share").font = FONT_LABEL_B
            for wi, w in enumerate(wacc_1d):
                if w <= sc_tgr:
                    ws.cell(row=r, column=2 + wi, value="N/A").font = FONT_WARNING
                else:
                    last_ufcf = sc_p["ufcf"][-1]
                    tv = last_ufcf * (1 + sc_tgr) / (w - sc_tgr)
                    disc = [1 / (1 + w)**t for t in range(1, NP + 1)]
                    sum_pv = sum(sc_p["ufcf"][i] * disc[i] for i in range(NP))
                    pv_tv = tv * disc[-1]
                    ev = sum_pv + pv_tv
                    eq = ev + sc_p["cash_bs"] - sc_p["debt_bs"]
                    price = eq / self.market["shares_outstanding"]
                    c = ws.cell(row=r, column=2 + wi, value=round(price, 2))
                    c.number_format = FMT_MONEY2
                    if abs(w - sc_wacc) < 0.001:
                        c.fill = FILL_HIGHLIGHT; c.font = FONT_VALUE_B

    def _build_scenario_summary(self):
        ws = self.wb.create_sheet("Scenario Summary")
        ws.sheet_properties.tabColor = "ED7D31"
        col1 = 1
        set_col_widths(ws, {1: 30, 2: 18, 3: 18, 4: 18, 5: 35})

        r = 1
        write_section_header(ws, r, col1, 5, "Scenario Summary — Price Targets"); r += 2

        ws.cell(row=r, column=2, value="Best").font = FONT_SUBHEADER
        ws.cell(row=r, column=2).fill = FILL_SCENARIO_B
        ws.cell(row=r, column=3, value="Base").font = FONT_SUBHEADER
        ws.cell(row=r, column=3).fill = FILL_SCENARIO_M
        ws.cell(row=r, column=4, value="Worst").font = FONT_SUBHEADER
        ws.cell(row=r, column=4).fill = FILL_SCENARIO_W
        ws.cell(row=r, column=5, value="Rationale").font = FONT_SUBHEADER
        r += 1

        rows = [
            ("Implied Price/Share", "implied_price", FMT_MONEY2),
            ("Current Market Price", None, FMT_MONEY2),
            ("Upside / Downside",   None, FMT_PCT),
            ("", None, None),
            ("WACC", "wacc", FMT_PCT2),
            ("Terminal Growth",  "tgr", FMT_PCT2),
            ("Enterprise Value", "ev", FMT_NUM),
            ("Equity Value",     "equity_value", FMT_NUM),
            ("TV % of EV",       "tv_pct_ev", FMT_PCT),
        ]

        for label, key, fmt in rows:
            if key is None and label == "":
                r += 1; continue
            ws.cell(row=r, column=col1, value=label).font = FONT_LABEL_B

            if key == "implied_price":
                for si, sc in enumerate(SCENARIO_NAMES):
                    c = ws.cell(row=r, column=2 + si, value=self.proj[sc][key])
                    c.number_format = fmt; c.font = FONT_TITLE
                    c.fill = [FILL_SCENARIO_B, FILL_SCENARIO_M, FILL_SCENARIO_W][si]
            elif label == "Current Market Price":
                for si in range(3):
                    c = ws.cell(row=r, column=2 + si, value=self.market["share_price"])
                    c.number_format = fmt; c.font = FONT_VALUE
            elif label == "Upside / Downside":
                for si, sc in enumerate(SCENARIO_NAMES):
                    upside = (self.proj[sc]["implied_price"] / self.market["share_price"]) - 1
                    c = ws.cell(row=r, column=2 + si, value=round(upside, 4))
                    c.number_format = fmt
                    c.font = FONT_CHECK_OK if upside > 0 else FONT_WARNING
            elif key:
                for si, sc in enumerate(SCENARIO_NAMES):
                    c = ws.cell(row=r, column=2 + si, value=self.proj[sc][key])
                    c.number_format = fmt; c.font = FONT_VALUE
            r += 1

    def _build_notes(self):
        ws = self.wb.create_sheet("Notes & Assumptions")
        ws.sheet_properties.tabColor = "A5A5A5"
        set_col_widths(ws, {1: 5, 2: 30, 3: 60})

        r = 1
        write_section_header(ws, r, 2, 3, "Notes & Key Assumptions"); r += 2

        for key, text in RATIONALE.items():
            label = key.replace("_", " ").title()
            ws.cell(row=r, column=2, value=label).font = FONT_LABEL_B
            ws.cell(row=r, column=3, value=text).font = FONT_LABEL
            ws.cell(row=r, column=3).alignment = ALIGN_LEFT
            r += 1

        r += 2
        write_subheader(ws, r, 2, 3, "Data Sources"); r += 1
        sources = [
            ("Historical Financials", "SEC EDGAR XBRL API (CIK 0000320193)"),
            ("Market Data", "Yahoo Finance (yfinance Python library)"),
            ("Risk-Free Rate", "FRED — 10-Year US Treasury Yield (DGS10)"),
            ("Expected Inflation", "FRED — 10-Year Breakeven Inflation (T10YIE)"),
            ("Market Risk Premium", "Damodaran (NYU Stern) Country Risk Premium dataset"),
            ("Segment Revenue", "Apple 10-K filings (iPhone, Mac, iPad, Wearables, Services)"),
        ]
        for label, source in sources:
            ws.cell(row=r, column=2, value=label).font = FONT_LABEL
            ws.cell(row=r, column=3, value=source).font = FONT_SMALL
            r += 1
