"""
QQQ High Growth Screener — Config & Fallback Data
===================================================
User-tunable config lives at the top. The hardcoded NASDAQ-100 list is
only used if the live Wikipedia fetch fails.
"""

# ═══════════════════════════════════════════════════════════════
#  USER CONFIG  (edit these)
# ═══════════════════════════════════════════════════════════════

# Rank range to screen (1 = largest market cap in the index)
RANK_MIN = 15
RANK_MAX = 100

# Checklist thresholds
REV_GROWTH_THRESHOLD   = 0.15   # Check 1: YoY revenue growth must exceed this
GROSS_MARGIN_THRESHOLD = 0.50   # Check 3: gross margin must exceed this
RULE_OF_40_THRESHOLD   = 40.0   # Check 4: rev growth % + FCF margin % must exceed this

# Signal cutoffs (score out of 5)
BUY_SCORE   = 5   # 🟢
WATCH_SCORE = 4   # 🟡
# anything below WATCH_SCORE → 🔴 skip

# Politeness delay between yfinance calls (seconds) to avoid rate limits
RATE_LIMIT_SLEEP = 0.5

# ═══════════════════════════════════════════════════════════════
#  Data sources
# ═══════════════════════════════════════════════════════════════

WIKI_URL = "https://en.wikipedia.org/wiki/Nasdaq-100"

# ═══════════════════════════════════════════════════════════════
#  Fallback NASDAQ-100 constituents
#  (used only if the Wikipedia fetch fails; list drifts over time)
# ═══════════════════════════════════════════════════════════════

FALLBACK_NASDAQ100 = [
    "AAPL", "MSFT", "NVDA", "AMZN", "AVGO", "META", "TSLA", "GOOGL", "GOOG",
    "COST", "NFLX", "TMUS", "CSCO", "ADBE", "PEP", "AMD", "LIN", "INTU",
    "TXN", "QCOM", "ISRG", "AMGN", "BKNG", "HON", "AMAT", "CMCSA", "PANW",
    "ADP", "VRTX", "GILD", "ADI", "MU", "MELI", "LRCX", "REGN", "KLAC",
    "SBUX", "CRWD", "SNPS", "CDNS", "MDLZ", "PYPL", "MAR", "CTAS", "ORLY",
    "ASML", "NXPI", "ABNB", "PDD", "FTNT", "DASH", "WDAY", "ROP", "MNST",
    "AEP", "CPRT", "ADSK", "PCAR", "ROST", "CHTR", "KDP", "PAYX", "FANG",
    "NDAQ", "ODFL", "FAST", "EA", "KHC", "VRSK", "CTSH", "EXC", "GEHC",
    "CCEP", "XEL", "LULU", "TTWO", "IDXX", "BKR", "DXCM", "CSGP", "ZS",
    "ANSS", "ON", "TEAM", "MCHP", "CDW", "BIIB", "GFS", "WBD", "DDOG",
    "ARM", "MRVL", "SMCI", "MDB", "PLTR", "APP", "LIN",
]
