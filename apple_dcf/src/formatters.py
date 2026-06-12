"""
Apple DCF Model — Excel Formatting Helpers
============================================
Professional finance-model styling for openpyxl.
"""

from openpyxl.styles import (
    Font, PatternFill, Alignment, Border, Side, numbers, NamedStyle
)
from openpyxl.comments import Comment
from openpyxl.utils import get_column_letter

# ═══════════════════════════════════════════════════════════════
#  Color Palette  (finance-model standard)
# ═══════════════════════════════════════════════════════════════

C_DARK_BLUE   = "1F3864"
C_MED_BLUE    = "2E75B6"
C_LIGHT_BLUE  = "D6E4F0"
C_NAVY        = "002060"
C_WHITE       = "FFFFFF"
C_BLACK       = "000000"
C_LIGHT_GRAY  = "F2F2F2"
C_MED_GRAY    = "D9D9D9"
C_GREEN       = "548235"
C_LIGHT_GREEN = "E2EFDA"
C_RED         = "C00000"
C_LIGHT_RED   = "FCE4EC"
C_ORANGE      = "ED7D31"
C_YELLOW      = "FFF2CC"
C_LIGHT_YELLOW= "FFFFF0"

# ═══════════════════════════════════════════════════════════════
#  Fonts
# ═══════════════════════════════════════════════════════════════

FONT_TITLE     = Font(name="Calibri", size=18, bold=True, color=C_NAVY)
FONT_SUBTITLE  = Font(name="Calibri", size=12, bold=True, color=C_DARK_BLUE)
FONT_HEADER    = Font(name="Calibri", size=10, bold=True, color=C_WHITE)
FONT_SUBHEADER = Font(name="Calibri", size=10, bold=True, color=C_DARK_BLUE)
FONT_LABEL     = Font(name="Calibri", size=10, color=C_BLACK)
FONT_LABEL_B   = Font(name="Calibri", size=10, bold=True, color=C_BLACK)
FONT_VALUE     = Font(name="Calibri", size=10, color=C_BLACK)
FONT_VALUE_B   = Font(name="Calibri", size=10, bold=True, color=C_NAVY)
FONT_SMALL     = Font(name="Calibri", size=9, color="808080")
FONT_LINK      = Font(name="Calibri", size=10, color=C_MED_BLUE, underline="single")
FONT_KPI       = Font(name="Calibri", size=10, italic=True, color=C_DARK_BLUE)
FONT_WARNING   = Font(name="Calibri", size=10, bold=True, color=C_RED)
FONT_CHECK_OK  = Font(name="Calibri", size=10, bold=True, color=C_GREEN)

# ═══════════════════════════════════════════════════════════════
#  Fills
# ═══════════════════════════════════════════════════════════════

FILL_HEADER     = PatternFill("solid", fgColor=C_DARK_BLUE)
FILL_SUBHEADER  = PatternFill("solid", fgColor=C_LIGHT_BLUE)
FILL_INPUT      = PatternFill("solid", fgColor=C_YELLOW)
FILL_CALC       = PatternFill("solid", fgColor=C_LIGHT_GRAY)
FILL_HIGHLIGHT  = PatternFill("solid", fgColor=C_LIGHT_GREEN)
FILL_WARNING    = PatternFill("solid", fgColor=C_LIGHT_RED)
FILL_DIVIDER    = PatternFill("solid", fgColor=C_NAVY)
FILL_SCENARIO_B = PatternFill("solid", fgColor="D5E8D4")  # Best
FILL_SCENARIO_M = PatternFill("solid", fgColor=C_LIGHT_BLUE)  # Base
FILL_SCENARIO_W = PatternFill("solid", fgColor="F8CECC")  # Worst
FILL_WHITE      = PatternFill("solid", fgColor=C_WHITE)

# ═══════════════════════════════════════════════════════════════
#  Borders
# ═══════════════════════════════════════════════════════════════

THIN   = Side(style="thin",   color=C_MED_GRAY)
MEDIUM = Side(style="medium", color=C_BLACK)
HAIR   = Side(style="hair",   color=C_MED_GRAY)

BORDER_THIN    = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
BORDER_BOTTOM  = Border(bottom=MEDIUM)
BORDER_TOP     = Border(top=MEDIUM)
BORDER_TB      = Border(top=MEDIUM, bottom=MEDIUM)
BORDER_ALL     = Border(left=THIN, right=THIN, top=THIN, bottom=MEDIUM)

# ═══════════════════════════════════════════════════════════════
#  Alignment
# ═══════════════════════════════════════════════════════════════

ALIGN_LEFT    = Alignment(horizontal="left",   vertical="center", wrap_text=True)
ALIGN_CENTER  = Alignment(horizontal="center", vertical="center")
ALIGN_RIGHT   = Alignment(horizontal="right",  vertical="center")

# ═══════════════════════════════════════════════════════════════
#  Number Formats
# ═══════════════════════════════════════════════════════════════

FMT_NUM     = '#,##0'           # 123,456
FMT_NUM1    = '#,##0.0'         # 123,456.0
FMT_DEC2    = '#,##0.00'        # 123,456.00
FMT_PCT     = '0.0%'            # 12.3%
FMT_PCT2    = '0.00%'           # 12.34%
FMT_MONEY   = '$#,##0'          # $123,456
FMT_MONEY2  = '$#,##0.00'       # $123,456.00
FMT_MULT    = '0.0x'            # 1.5x
FMT_DAYS    = '#,##0.0'         # 30.5
FMT_NEG_RED = '#,##0;[Red](#,##0)'

# ═══════════════════════════════════════════════════════════════
#  Helper Functions
# ═══════════════════════════════════════════════════════════════

def write_section_header(ws, row, col_start, col_end, title):
    """Write a dark-blue section header spanning multiple columns."""
    for c in range(col_start, col_end + 1):
        cell = ws.cell(row=row, column=c)
        cell.fill = FILL_HEADER
        cell.border = BORDER_THIN
    cell = ws.cell(row=row, column=col_start, value=title)
    cell.font = FONT_HEADER
    cell.alignment = ALIGN_LEFT
    ws.merge_cells(
        start_row=row, start_column=col_start,
        end_row=row,   end_column=col_end
    )


def write_subheader(ws, row, col_start, col_end, title):
    """Write a light-blue sub-header."""
    for c in range(col_start, col_end + 1):
        cell = ws.cell(row=row, column=c)
        cell.fill = FILL_SUBHEADER
        cell.border = BORDER_THIN
    cell = ws.cell(row=row, column=col_start, value=title)
    cell.font = FONT_SUBHEADER
    cell.alignment = ALIGN_LEFT


def write_row_data(ws, row, label, values, col_start=1, val_start=2,
                   label_font=FONT_LABEL, val_font=FONT_VALUE,
                   val_fmt=FMT_NUM, is_total=False):
    """
    Write a label + list of values across columns.
    col_start = column for label, val_start = column for first value.
    """
    cell = ws.cell(row=row, column=col_start, value=label)
    cell.font = FONT_LABEL_B if is_total else label_font
    cell.alignment = ALIGN_LEFT
    if is_total:
        cell.border = BORDER_TOP

    for i, v in enumerate(values):
        c = ws.cell(row=row, column=val_start + i, value=v)
        c.font = FONT_VALUE_B if is_total else val_font
        c.number_format = val_fmt
        c.alignment = ALIGN_RIGHT
        if is_total:
            c.border = BORDER_TOP


def write_year_headers(ws, row, years, col_start=2, hist_count=5):
    """Write FY year headers with historical vs forecast color coding."""
    for i, yr in enumerate(years):
        cell = ws.cell(row=row, column=col_start + i, value=f"FY{yr}")
        cell.font = FONT_HEADER
        cell.alignment = ALIGN_CENTER
        cell.border = BORDER_THIN
        cell.fill = FILL_HEADER


def write_scenario_headers(ws, row, col_start, num_years=10):
    """Write Best / Base / Worst scenario column headers."""
    labels = ["Best Case", "Base Case", "Worst Case"]
    fills  = [FILL_SCENARIO_B, FILL_SCENARIO_M, FILL_SCENARIO_W]
    for si, (label, fill) in enumerate(zip(labels, fills)):
        start_col = col_start + si * num_years
        for j in range(num_years):
            c = ws.cell(row=row, column=start_col + j)
            c.fill = fill
            c.border = BORDER_THIN
        c = ws.cell(row=row, column=start_col, value=label)
        c.font = FONT_SUBHEADER
        c.alignment = ALIGN_CENTER
        ws.merge_cells(
            start_row=row, start_column=start_col,
            end_row=row,   end_column=start_col + num_years - 1
        )


def add_comment(cell, text, author="DCF Model"):
    """Attach an Excel comment to a cell."""
    cell.comment = Comment(text, author, width=300, height=100)


def set_col_widths(ws, widths):
    """Set column widths. widths = {col_letter_or_num: width}."""
    for col, w in widths.items():
        if isinstance(col, int):
            col = get_column_letter(col)
        ws.column_dimensions[col].width = w


def auto_width(ws, min_width=10, max_width=18):
    """Auto-fit column widths based on content (approximate)."""
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            if cell.value:
                max_len = max(max_len, len(str(cell.value)))
        adjusted = min(max(max_len + 2, min_width), max_width)
        ws.column_dimensions[col_letter].width = adjusted


def format_divider_tab(ws, title):
    """Create a divider/separator tab (colored background, single title)."""
    ws.sheet_properties.tabColor = C_NAVY
    cell = ws.cell(row=3, column=2, value=title)
    cell.font = Font(name="Calibri", size=24, bold=True, color=C_WHITE)
    cell.alignment = ALIGN_CENTER
    for r in range(1, 8):
        for c in range(1, 8):
            ws.cell(row=r, column=c).fill = FILL_DIVIDER
    set_col_widths(ws, {1: 5, 2: 40})
