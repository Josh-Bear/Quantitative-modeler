"""Build output/report/final_report.pdf from the existing backtest outputs.

Run from the project root after a backtest exists (run.py already calls this
automatically at the end of a run):

    python make_pdf.py
"""
from src import report_pdf

if __name__ == "__main__":
    report_pdf.build_pdf_report()
