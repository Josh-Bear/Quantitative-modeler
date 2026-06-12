#!/usr/bin/env python3
"""
DCF Model — Local Dev Server + Yahoo Finance Proxy (yfinance edition)
=====================================================================
รัน: python3 server.py
เปิด: http://localhost:8765

Endpoints:
  GET /                    → serves index.html
  GET /api/fetch?ticker=XX → returns normalised company data via yfinance
  GET /<file>              → serves static files (css, js)

Dependencies:
  pip3 install yfinance
"""

import http.server
import urllib.parse
import json
import sys
import os
import socketserver
import traceback

PORT = 8765
STATIC_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Industry mapping: yfinance sector → our dropdown ─────────────
SECTOR_MAP = {
    'Technology':            'Technology',
    'Healthcare':            'Healthcare',
    'Consumer Defensive':    'Consumer Staples',
    'Consumer Cyclical':     'Consumer Discretionary',
    'Financial Services':    'Financials',
    'Energy':                'Energy',
    'Industrials':           'Industrials',
    'Real Estate':           'Real Estate',
    'Communication Services':'Telecommunications',
    'Utilities':             'Utilities',
    'Basic Materials':       'Materials',
}


def get_stock_data(ticker: str) -> dict:
    """Fetch and normalise stock data using yfinance."""
    import yfinance as yf

    stock = yf.Ticker(ticker)
    info  = stock.info  # dict with 200+ fields

    if not info or info.get('trailingPps') == 0:
        # yfinance sometimes returns empty dict for bad tickers
        if not info.get('shortName') and not info.get('longName'):
            raise ValueError(f"No data found for ticker '{ticker}'")

    # ── Revenue ────────────────────────────────────────────────────
    total_revenue = info.get('totalRevenue')

    # ── Margins ───────────────────────────────────────────────────
    ebit_margin = info.get('ebitdaMargins') or info.get('operatingMargins')
    # prefer operatingMargins (closer to EBIT) if both present
    op_margin   = info.get('operatingMargins')
    if op_margin is not None:
        ebit_margin = op_margin

    # ── Debt & Cash ───────────────────────────────────────────────
    total_debt  = info.get('totalDebt',   0) or 0
    total_cash  = info.get('totalCash',   0) or 0

    # ── Growth ────────────────────────────────────────────────────
    rev_growth = info.get('revenueGrowth')   # trailing YoY
    # also check earningsGrowth as fallback
    if rev_growth is None:
        rev_growth = info.get('earningsGrowth')

    # ── Beta & Shares ─────────────────────────────────────────────
    beta             = info.get('beta')
    shares_out       = info.get('sharesOutstanding')

    # ── Company meta ──────────────────────────────────────────────
    company_name = info.get('longName') or info.get('shortName') or ticker
    sector       = info.get('sector', '')
    industry     = info.get('industry', '')
    mapped_sector = SECTOR_MAP.get(sector, '')

    return {
        'ticker':            ticker.upper(),
        'companyName':       company_name,
        'sector':            sector,
        'industry':          industry,
        'mappedSector':      mapped_sector,
        'totalRevenue':      total_revenue,
        'ebitMargins':       ebit_margin,
        'totalDebt':         total_debt,
        'totalCash':         total_cash,
        'revenueGrowth':     rev_growth,
        'beta':              beta,
        'sharesOutstanding': shares_out,
    }


class DCFHandler(http.server.SimpleHTTPRequestHandler):
    """Serves static files and proxies data via yfinance."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=STATIC_DIR, **kwargs)

    def log_message(self, fmt, *args):
        path = args[0] if args else ''
        if '/api/' in str(path):
            print(f"  🔍 {fmt % args}")

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == '/api/fetch':
            self._handle_fetch(parsed.query)
        else:
            super().do_GET()

    def _handle_fetch(self, query_string: str):
        params = urllib.parse.parse_qs(query_string)
        ticker = params.get('ticker', [''])[0].strip().upper()

        if not ticker:
            self._json_error(400, 'ticker parameter required')
            return

        print(f"  ↗  Fetching {ticker} via yfinance...")

        try:
            data = get_stock_data(ticker)
            self._json_ok(data)
            print(f"  ✅ {ticker}: rev={data.get('totalRevenue')}, "
                  f"beta={data.get('beta')}, "
                  f"sector={data.get('sector')}")

        except ImportError:
            msg = 'yfinance not installed. Run: pip3 install yfinance'
            print(f'  ❌ {msg}')
            self._json_error(500, msg)

        except Exception as e:
            msg = str(e)
            print(f'  ❌ Error for {ticker}: {msg}')
            traceback.print_exc()
            self._json_error(404, f'Could not fetch data for {ticker}: {msg}')

    def _json_ok(self, data: dict):
        body = json.dumps({'ok': True, 'data': data}).encode()
        self._send_json(200, body)

    def _json_error(self, code: int, message: str):
        body = json.dumps({'ok': False, 'error': message}).encode()
        self._send_json(code, body)

    def _send_json(self, code: int, body: bytes):
        self.send_response(code)
        self.send_header('Content-Type',   'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)


# ── Main ─────────────────────────────────────────────────────────
if __name__ == '__main__':
    os.chdir(STATIC_DIR)

    # Test yfinance import early
    try:
        import yfinance  # noqa: F401
    except ImportError:
        print('\n❌  yfinance is not installed.')
        print('    Run: pip3 install yfinance\n')
        sys.exit(1)

    with socketserver.TCPServer(('', PORT), DCFHandler) as httpd:
        httpd.allow_reuse_address = True
        print(f'\n{"="*55}')
        print(f'  🚀  DCF Model Server running')
        print(f'  🌐  http://localhost:{PORT}/')
        print(f'  📡  Fetch: /api/fetch?ticker=AAPL')
        print(f'  {"─"*49}')
        print(f'  Press Ctrl+C to stop')
        print(f'{"="*55}\n')
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print('\n  👋  Server stopped.')
            sys.exit(0)
