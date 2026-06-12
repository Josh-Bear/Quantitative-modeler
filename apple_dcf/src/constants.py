"""
Apple DCF Model — Constants & Fallback Data
=============================================
Hardcoded Apple financial data from 10-K filings as fallback
if live fetch fails.  All monetary values in USD millions.
"""

# ═══════════════════════════════════════════════════════════════
#  Company Metadata
# ═══════════════════════════════════════════════════════════════

COMPANY     = "Apple Inc."
TICKER      = "AAPL"
CIK         = "0000320193"
CURRENCY    = "USD"
FY_END_MONTH = 9  # September

HIST_YEARS  = [2020, 2021, 2022, 2023, 2024]
PROJ_YEARS  = list(range(2025, 2035))          # 10-year forecast
ALL_YEARS   = HIST_YEARS + PROJ_YEARS

# SEC EDGAR request header
SEC_HEADERS = {
    "User-Agent": "AppleDCFResearch research@quantmodel.dev",
    "Accept-Encoding": "gzip, deflate",
}

# ═══════════════════════════════════════════════════════════════
#  Fallback Macro / Market Data  (§11 of brief)
# ═══════════════════════════════════════════════════════════════

FALLBACK = {
    "share_price":        291.58,
    "shares_outstanding": 14750,     # millions
    "beta":               1.09,
    "risk_free_rate":     0.0455,    # 10Y UST
    "expected_inflation": 0.030,
    "market_risk_premium":0.050,
    "effective_tax_rate": 0.16,
    "cost_of_debt":       0.050,
}

# ═══════════════════════════════════════════════════════════════
#  Historical Income Statement  (from Apple 10-K filings)
#  All values in USD millions
# ═══════════════════════════════════════════════════════════════

HIST_INCOME = {
    #                          FY2020     FY2021     FY2022     FY2023     FY2024
    "total_revenue":        [274_515, 365_817, 394_328, 383_285, 391_035],
    "products_revenue":     [220_747, 297_392, 316_199, 298_085, 294_866],
    "services_revenue":     [ 53_768,  68_425,  78_129,  85_200,  96_169],

    "products_cogs":        [151_286, 192_266, 201_471, 205_074, 201_093],
    "services_cogs":        [ 18_273,  22_075,  22_075,  24_855,  25_550],
    "total_cogs":           [169_559, 214_341, 223_546, 229_929, 226_643],
    "gross_profit":         [104_956, 151_476, 170_782, 153_356, 164_392],

    "rd_expense":           [ 18_752,  21_914,  26_251,  29_915,  31_370],
    "sga_expense":          [ 19_916,  21_973,  25_094,  24_932,  26_146],
    "total_opex":           [ 38_668,  43_887,  51_345,  54_847,  57_516],
    "operating_income":     [ 66_288, 107_589, 119_437,  98_509, 106_876],

    "other_income_expense": [    803,     198,    -334,    -565,     269],
    "pretax_income":        [ 67_091, 107_787, 119_103,  97_944, 107_145],
    "tax_provision":        [  9_680,  14_527,  19_300,  16_741,  16_171],
    "net_income":           [ 57_411,  93_260,  99_803,  81_203,  90_974],
}

# ═══════════════════════════════════════════════════════════════
#  Historical Segment Revenue  (from Apple 10-K filings)
# ═══════════════════════════════════════════════════════════════

HIST_SEGMENTS = {
    #                     FY2020     FY2021     FY2022     FY2023     FY2024
    "iPhone":          [137_781, 191_973, 205_489, 200_583, 201_183],
    "Mac":             [ 28_622,  35_190,  40_177,  29_357,  29_984],
    "iPad":            [ 23_724,  31_862,  29_292,  28_300,  26_694],
    "Wearables":       [ 30_620,  38_367,  41_241,  39_845,  37_005],
    "Services":        [ 53_768,  68_425,  78_129,  85_200,  96_169],
}

# ═══════════════════════════════════════════════════════════════
#  Historical Balance Sheet  (from Apple 10-K filings)
# ═══════════════════════════════════════════════════════════════

HIST_BALANCE = {
    #                                  FY2020     FY2021     FY2022     FY2023     FY2024
    "cash_and_equivalents":         [ 38_016,  34_940,  23_646,  29_965,  29_943],
    "short_term_investments":       [ 52_927,  27_699,  24_658,  31_590,  35_228],
    "accounts_receivable":          [ 16_120,  26_278,  28_184,  29_508,  34_774],
    "inventory":                    [  4_061,   6_580,   6_331,   6_331,   7_286],
    "other_current_assets":         [ 32_411,  39_263,  52_583,  43_621,  42_751],
    "total_current_assets":         [143_535, 134_760, 135_402, 143_566, 152_987],

    "ppe_net":                      [ 36_766,  39_440,  42_117,  43_715,  44_856],
    "goodwill_intangibles":         [     0,       0,       0,       0,       0],
    "other_non_current_assets":     [170_473, 177_094, 175_463, 165_572, 167_024],
    "total_assets":                 [323_888, 351_002, 352_755, 352_583, 364_980],

    "accounts_payable":             [ 42_296,  54_763,  64_115,  62_611,  68_960],
    "short_term_debt":              [ 13_769,  15_613,  21_110,  15_807,  10_912],
    "other_current_liabilities":    [ 49_327,  55_283,  68_655,  69_921,  66_609],
    "total_current_liabilities":    [105_392, 125_481, 153_982, 145_308, 176_392],

    "long_term_debt":               [112_436, 109_106,  98_959, 106_572,  96_807],
    "other_non_current_liabilities":[ 54_490,  53_325,  49_142,  50_202,  46_108],
    "total_liabilities":            [258_549, 287_912, 302_083, 290_437, 308_030],

    "stockholders_equity":          [ 65_339,  63_090,  50_672,  62_146,  56_950],
}

# ═══════════════════════════════════════════════════════════════
#  Other Historical Derived Data
# ═══════════════════════════════════════════════════════════════

HIST_OTHER = {
    #                       FY2020   FY2021   FY2022   FY2023   FY2024
    "depreciation":       [11_056,  11_284,  11_104,  11_519,  11_445],
    "capex":              [ 7_309,  11_085,  10_708,  10_959,  10_959],
    "interest_expense":   [ 2_873,   2_645,   2_931,   3_933,   3_600],
    "dividends_paid":     [14_081,  14_467,  14_841,  15_025,  15_234],
    "share_repurchases":  [72_358,  85_502,  89_402,  77_550,  94_949],
}

# ═══════════════════════════════════════════════════════════════
#  Scenario Assumptions  (§7 of brief)
# ═══════════════════════════════════════════════════════════════

SCENARIOS = {
    "iPhone_growth": {
        "Best":  [0.08, 0.07, 0.06, 0.05, 0.05, 0.04, 0.04, 0.03, 0.03, 0.03],
        "Base":  [0.04, 0.03, 0.03, 0.02, 0.02, 0.02, 0.02, 0.02, 0.02, 0.02],
        "Worst": [0.00, -0.01, -0.01, -0.02, -0.02, -0.01, -0.01, 0.00, 0.00, 0.00],
    },
    "Mac_growth": {
        "Best":  [0.08, 0.07, 0.06, 0.05, 0.04, 0.03, 0.03, 0.03, 0.02, 0.02],
        "Base":  [0.03, 0.03, 0.02, 0.02, 0.02, 0.01, 0.01, 0.01, 0.01, 0.01],
        "Worst": [0.00, 0.00, 0.00, -0.01, -0.01, 0.00, 0.00, 0.00, 0.00, 0.00],
    },
    "iPad_growth": {
        "Best":  [0.06, 0.05, 0.04, 0.04, 0.03, 0.03, 0.02, 0.02, 0.02, 0.02],
        "Base":  [0.02, 0.02, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01],
        "Worst": [-0.02, -0.02, -0.01, -0.01, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00],
    },
    "Wearables_growth": {
        "Best":  [0.10, 0.09, 0.08, 0.07, 0.06, 0.05, 0.04, 0.04, 0.03, 0.03],
        "Base":  [0.03, 0.02, 0.02, 0.02, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01],
        "Worst": [0.00, 0.00, -0.01, -0.01, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00],
    },
    "Services_growth": {
        "Best":  [0.15, 0.14, 0.13, 0.12, 0.12, 0.11, 0.10, 0.10, 0.09, 0.09],
        "Base":  [0.12, 0.11, 0.10, 0.10, 0.09, 0.09, 0.08, 0.08, 0.08, 0.08],
        "Worst": [-0.05, 0.05, 0.06, 0.06, 0.06, 0.05, 0.05, 0.05, 0.05, 0.05],
    },

    "products_gp_pct": {
        "Best":  0.355,   # +1-2pp above base
        "Base":  0.340,   # ~3yr historical avg
        "Worst": 0.320,   # -1-2pp below base (tariffs/costs)
    },
    "services_gp_pct": {
        "Best":  0.760,
        "Base":  0.740,
        "Worst": 0.710,
    },

    "rd_pct_rev": {
        "Best":  0.077,
        "Base":  0.080,
        "Worst": 0.085,
    },
    "sga_pct_rev": {
        "Best":  0.062,
        "Base":  0.067,
        "Worst": 0.072,
    },
    "capex_pct_rev": {
        "Best":  0.028,
        "Base":  0.030,
        "Worst": 0.033,
    },
    "da_pct_ppe": {
        "Best":  0.27,
        "Base":  0.28,
        "Worst": 0.29,
    },
}

# Segment GP% differentials vs blended Products GP%
# (iPhone has higher margins than blended, Mac/iPad lower)
SEGMENT_GP_DIFF = {
    "iPhone":    +0.030,   # +3pp premium (scale, brand, ASP)
    "Mac":       -0.020,   # -2pp (more commoditized hardware)
    "iPad":      -0.020,   # -2pp (similar to Mac)
    "Wearables": +0.010,   # +1pp (higher-margin niche)
}

# Comparable companies for GP% rationale
SEGMENT_COMPARABLES = {
    "iPhone":    "Samsung IM (~18%), Xiaomi Smartphone (~12%); Apple commands significant premium",
    "Mac":       "Dell (~22%), HP (~22%); Apple similar with premium offset by lower volume",
    "iPad":      "Same PC comparables as Mac; tablet market more concentrated",
    "Wearables": "Garmin (~58%), Sonos (~45%); Apple's ecosystem integration drives premium",
}

# Working Capital assumptions (days)
WC_ASSUMPTIONS = {
    "dso": {"Best": 28, "Base": 30, "Worst": 35},
    "dio": {"Best":  6, "Base":  7, "Worst":  9},
    "dpo": {"Best": 65, "Base": 62, "Worst": 55},
}

# Terminal growth rate tied to inflation
TGR_OFFSET = {
    "Best":  +0.005,   # inflation + 0.5pp
    "Base":   0.000,   # = inflation
    "Worst": -0.005,   # inflation - 0.5pp
}

# WACC adjustment (basis points added to base WACC)
WACC_ADJ_BPS = {
    "Best":  -50,    # -0.50pp (benign macro)
    "Base":    0,
    "Worst": +75,    # +0.75pp (stressed macro)
}

# ═══════════════════════════════════════════════════════════════
#  Scenario Rationale Text  (for Excel comments)
# ═══════════════════════════════════════════════════════════════

RATIONALE = {
    "iPhone_growth_best":   "New product cycle (foldable/AI features) drives upgrade supercycle",
    "iPhone_growth_base":   "Historical 3yr avg growth, in line with analyst consensus",
    "iPhone_growth_worst":  "Mature market, longer replacement cycles, China competition",
    "Mac_growth_best":      "Apple Silicon transition continues to drive PC share gains",
    "Mac_growth_base":      "Flat-to-low single digit, in line with PC market growth",
    "Mac_growth_worst":     "Market saturation, no major refresh cycle",
    "iPad_growth_best":     "M-chip iPads expand addressable market into laptop territory",
    "iPad_growth_base":     "Flat-to-low single digit, in line with tablet market",
    "iPad_growth_worst":    "Category maturity, minimal refresh cycle innovation",
    "Wearables_growth_best":"New category launch (health features, smart glasses) reaccelerates growth",
    "Wearables_growth_base":"Continuation of recent slowing growth trend",
    "Wearables_growth_worst":"Category maturity, growth flattens",
    "Services_growth_best": "Continued 13-15% growth; Search deal survives antitrust",
    "Services_growth_base": "10-12% growth, moderating from recent highs",
    "Services_growth_worst":"Google Search-deal revenue (~$20bn) lost via antitrust ruling; slower growth",
    "products_gp_best":     "Mix shift toward Services + supply chain efficiencies → +1-2pp",
    "products_gp_base":     "Flat at 3yr historical average",
    "products_gp_worst":    "Tariff / input cost pressure compresses margin -1-2pp",
    "services_gp_best":     "Mix shift to high-margin advertising / subscriptions → +1pp",
    "services_gp_base":     "Flat at historical average (~74%)",
    "services_gp_worst":    "Regulatory pressure (App Store commission caps) → -2-3pp",
    "tgr_best":             "Long-run inflation + 0.5pp (Apple maintains real growth)",
    "tgr_base":             "= long-run inflation (nominal GDP growth proxy)",
    "tgr_worst":            "Long-run inflation - 0.5pp (real growth converges to zero)",
    "wacc_best":            "Lower risk premium in benign macro environment",
    "wacc_base":            "Base CAPM-derived WACC",
    "wacc_worst":           "Higher risk-free rate or beta in stressed macro environment",
}
