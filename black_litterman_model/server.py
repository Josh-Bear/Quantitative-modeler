#!/usr/bin/env python3
"""
Black-Litterman Optimizer — Local Dev Server + Yahoo Finance Proxy
==================================================================
รัน:  python3 server.py
เปิด: http://localhost:8770

Endpoints:
  GET /                          → serves index.html
  GET /api/data?tickers=A,B,C    → monthly prices (3yr) + market cap per ticker
  GET /<file>                    → serves static files (css, js)

Dependencies:
  pip3 install yfinance

ทุก request ผ่าน backend ตัวนี้เพื่อเลี่ยงปัญหา CORS ของ Yahoo Finance
(ตามที่ระบุไว้ใน BL_Optimizer_Plan.md → ข้อควรระวัง: CORS)
"""

import http.server
import urllib.parse
import json
import sys
import os
import socketserver
import traceback

PORT = 8770
STATIC_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PERIOD = "3y"


def get_history(tickers, period=DEFAULT_PERIOD):
    """Fetch monthly adjusted closes + market cap for each ticker via yfinance.

    Returns: { 'prices': {TICKER: [{date, close}, ...]}, 'marketCap': {TICKER: n},
               'meta': {TICKER: {name, sector}}, 'errors': {TICKER: msg} }
    """
    import yfinance as yf

    prices, market_cap, meta, errors = {}, {}, {}, {}

    for ticker in tickers:
        t = ticker.strip().upper()
        if not t:
            continue
        try:
            yt = yf.Ticker(t)
            hist = yt.history(period=period, interval="1mo", auto_adjust=True)
            if hist is None or hist.empty:
                errors[t] = "no price history"
                continue

            series = []
            for idx, row in hist.iterrows():
                close = row.get("Close")
                if close is None or close != close:  # skip NaN
                    continue
                series.append({"date": idx.strftime("%Y-%m"), "close": float(close)})

            if len(series) < 13:
                errors[t] = f"only {len(series)} monthly points (need ≥13)"
                continue

            prices[t] = series

            info = {}
            try:
                info = yt.info or {}
            except Exception:
                info = {}
            market_cap[t] = info.get("marketCap") or 0
            meta[t] = {
                "name": info.get("longName") or info.get("shortName") or t,
                "sector": info.get("sector", ""),
            }
            print(f"  ✅ {t}: {len(series)} months, mktCap={market_cap[t]}")

        except Exception as e:  # noqa: BLE001
            errors[t] = str(e)
            print(f"  ❌ {t}: {e}")

    return {"prices": prices, "marketCap": market_cap, "meta": meta, "errors": errors}


class BLHandler(http.server.SimpleHTTPRequestHandler):
    """Serves static files and proxies market data via yfinance."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=STATIC_DIR, **kwargs)

    def log_message(self, fmt, *args):
        path = args[0] if args else ""
        if "/api/" in str(path):
            print(f"  🔍 {fmt % args}")

    def end_headers(self):
        # Disable caching for JS/CSS so the browser always loads the latest file.
        if self.path.endswith(('.js', '.css')):
            self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Expires', '0')
        super().end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/data":
            self._handle_data(parsed.query)
        else:
            super().do_GET()

    def _handle_data(self, query_string):
        params = urllib.parse.parse_qs(query_string)
        raw = params.get("tickers", [""])[0]
        period = params.get("period", [DEFAULT_PERIOD])[0]
        tickers = [t for t in raw.split(",") if t.strip()]

        if not tickers:
            self._json_error(400, "tickers parameter required (comma-separated)")
            return

        print(f"  ↗  Fetching {tickers} (period={period}) via yfinance...")
        try:
            data = get_history(tickers, period=period)
            if not data["prices"]:
                self._json_error(404, f"no usable data for {tickers}: {data['errors']}")
                return
            self._json_ok(data)
        except ImportError:
            msg = "yfinance not installed. Run: pip3 install yfinance"
            print(f"  ❌ {msg}")
            self._json_error(500, msg)
        except Exception as e:  # noqa: BLE001
            print(f"  ❌ Error: {e}")
            traceback.print_exc()
            self._json_error(500, str(e))

    def _json_ok(self, data):
        self._send_json(200, json.dumps({"ok": True, "data": data}).encode())

    def _json_error(self, code, message):
        self._send_json(code, json.dumps({"ok": False, "error": message}).encode())

    def _send_json(self, code, body):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    os.chdir(STATIC_DIR)
    try:
        import yfinance  # noqa: F401
    except ImportError:
        print("\n❌  yfinance is not installed.")
        print("    Run: pip3 install yfinance\n")
        sys.exit(1)

    class ReusableTCPServer(socketserver.TCPServer):
        allow_reuse_address = True
        def server_bind(self):
            import socket
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except AttributeError:
                pass  # SO_REUSEPORT not available on all platforms
            super().server_bind()

    with ReusableTCPServer(("", PORT), BLHandler) as httpd:
        print(f'\n{"="*55}')
        print("  🚀  Black-Litterman Optimizer running")
        print(f"  🌐  http://localhost:{PORT}/")
        print("  📡  Data: /api/data?tickers=AAPL,MSFT,GOOGL")
        print(f'  {"─"*49}')
        print("  Press Ctrl+C to stop")
        print(f'{"="*55}\n')
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n  👋  Server stopped.")
            sys.exit(0)
