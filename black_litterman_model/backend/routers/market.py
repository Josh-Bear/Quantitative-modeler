"""
GET /api/data  — yfinance proxy (monthly prices + market cap).
Mirrors the logic from the original server.py _handle_data().
"""
import asyncio
from functools import partial

import yfinance as yf
from fastapi import APIRouter, HTTPException, Query

router = APIRouter()

DEFAULT_PERIOD = "3y"


def _fetch_sync(tickers: list[str], period: str) -> dict:
    """Run yfinance calls synchronously (offloaded to thread pool)."""
    prices, market_cap, meta, errors = {}, {}, {}, {}

    for t in tickers:
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

            info: dict = {}
            try:
                info = yt.info or {}
            except Exception:
                info = {}

            market_cap[t] = info.get("marketCap") or 0
            meta[t] = {
                "name": info.get("longName") or info.get("shortName") or t,
                "sector": info.get("sector", ""),
            }
            print(f"  ✅  {t}: {len(series)} months, mktCap={market_cap[t]}")

        except Exception as e:
            errors[t] = str(e)
            print(f"  ❌  {t}: {e}")

    return {"prices": prices, "marketCap": market_cap, "meta": meta, "errors": errors}


@router.get("/data")
async def get_data(
    tickers: str = Query(..., description="Comma-separated ticker symbols"),
    period: str = Query(DEFAULT_PERIOD, description="yfinance period string, e.g. 3y"),
):
    ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    if not ticker_list:
        raise HTTPException(400, "tickers parameter required (comma-separated)")

    print(f"  ↗  Fetching {ticker_list} (period={period}) ...")

    # yfinance is synchronous — run in a thread so we don't block the event loop
    loop = asyncio.get_event_loop()
    data = await loop.run_in_executor(None, partial(_fetch_sync, ticker_list, period))

    if not data["prices"]:
        raise HTTPException(404, f"no usable data for {ticker_list}: {data['errors']}")

    return {"ok": True, "data": data}
