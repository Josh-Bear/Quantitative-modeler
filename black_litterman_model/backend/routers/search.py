"""
GET /api/search?q=<query>  — live ticker autocomplete via yf.Search.
"""
import asyncio
from functools import partial

import yfinance as yf
from fastapi import APIRouter, Query

router = APIRouter()


def _search_sync(q: str) -> list[dict]:
    try:
        s = yf.Search(q, max_results=8, news_count=0)
        results = []
        for item in (s.quotes or []):
            sym = item.get("symbol", "")
            if not sym:
                continue
            results.append({
                "symbol": sym,
                "name": item.get("longname") or item.get("shortname") or sym,
                "exchange": item.get("exchange", ""),
                "type": item.get("quoteType", ""),
            })
        return results
    except Exception as e:
        print(f"  ⚠️   Search '{q}': {e}")
        return []


@router.get("/search")
async def search_tickers(q: str = Query("", description="Search query")):
    if not q.strip():
        return {"ok": True, "data": {"results": []}}

    loop = asyncio.get_event_loop()
    results = await loop.run_in_executor(None, partial(_search_sync, q.strip()))
    return {"ok": True, "data": {"results": results}}
