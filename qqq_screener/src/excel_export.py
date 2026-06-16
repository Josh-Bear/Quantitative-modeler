"""
QQQ High Growth Screener — Excel Export
=========================================
Writes a 3-sheet workbook:
  1. Screener Results — every ticker, raw data + checks + score + signal
  2. Shortlist        — score >= WATCH_SCORE, sorted by score
  3. Data Quality     — tickers with missing fields or fetch errors
"""

import logging

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from constants import WATCH_SCORE

log = logging.getLogger("excel")

HEADER_FILL = PatternFill("solid", fgColor="1F3864")
HEADER_FONT = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
GREEN_FILL  = PatternFill("solid", fgColor="E2EFDA")
YELLOW_FILL = PatternFill("solid", fgColor="FFF2CC")
RED_FILL    = PatternFill("solid", fgColor="FCE4EC")
THIN = Side(style="thin", color="D9D9D9")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

COLUMNS = [
    ("Ticker",        "Ticker"),
    ("Rev Growth",    "RevGrowth"),
    ("Accelerating",  "Accelerating"),
    ("Gross Margin",  "GrossMargin"),
    ("GM Expanding",  "GMExpanding"),
    ("Rule of 40",    "RuleOf40"),
    ("FCF ($)",       "FCF"),
    ("Fwd EPS",       "ForwardEps"),
    ("Trail EPS",     "TrailingEps"),
    ("Analyst Rev",   "AnalystRevise"),
    ("Score",         "Score"),
    ("Signal",        "Signal"),
]


def _fmt(key, val):
    """Human-readable cell value for a result field."""
    if val is None:
        return "N/A"
    if key in ("RevGrowth", "GrossMargin"):
        return round(val * 100, 1) if val < 2 else round(val, 1)  # pct
    if key == "RuleOf40":
        return round(val, 1)
    if key == "FCF":
        return round(val / 1e6, 1)   # → millions
    if key in ("ForwardEps", "TrailingEps"):
        return round(val, 2)
    if key in ("Accelerating", "GMExpanding", "AnalystRevise"):
        return {True: "✅", False: "❌"}.get(val, "N/A")
    return val


def _write_sheet(ws, rows):
    # header
    for c, (label, _) in enumerate(COLUMNS, 1):
        cell = ws.cell(row=1, column=c, value=label)
        cell.fill, cell.font = HEADER_FILL, HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = BORDER
    # body
    for r, res in enumerate(rows, 2):
        score = res.get("Score", 0)
        fill = (GREEN_FILL if score >= 5 else
                YELLOW_FILL if score >= WATCH_SCORE else RED_FILL)
        for c, (_, key) in enumerate(COLUMNS, 1):
            cell = ws.cell(row=r, column=c, value=_fmt(key, res.get(key)))
            cell.alignment = Alignment(horizontal="center")
            cell.border = BORDER
            if key in ("Score", "Signal", "Ticker"):
                cell.fill = fill
    # widths + freeze
    for c, (label, _) in enumerate(COLUMNS, 1):
        ws.column_dimensions[get_column_letter(c)].width = max(11, len(label) + 2)
    ws.freeze_panes = "A2"


def export(results: list, data_quality: list, path: str):
    wb = Workbook()

    ws1 = wb.active
    ws1.title = "Screener Results"
    _write_sheet(ws1, results)

    ws2 = wb.create_sheet("Shortlist")
    shortlist = sorted(
        [r for r in results if r.get("Score", 0) >= WATCH_SCORE],
        key=lambda r: r["Score"], reverse=True,
    )
    _write_sheet(ws2, shortlist)

    ws3 = wb.create_sheet("Data Quality")
    ws3.cell(row=1, column=1, value="Ticker").font = HEADER_FONT
    ws3.cell(row=1, column=1).fill = HEADER_FILL
    ws3.cell(row=1, column=2, value="Issue").font = HEADER_FONT
    ws3.cell(row=1, column=2).fill = HEADER_FILL
    for r, row in enumerate(data_quality, 2):
        ws3.cell(row=r, column=1, value=row["Ticker"])
        ws3.cell(row=r, column=2, value=row["Issue"])
    ws3.column_dimensions["A"].width = 12
    ws3.column_dimensions["B"].width = 60
    ws3.freeze_panes = "A2"

    wb.save(path)
    log.info(f"Excel written: {path}")
