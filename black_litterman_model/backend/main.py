"""
Black-Litterman Optimizer — FastAPI Backend
===========================================
รัน (dev):  uvicorn main:app --reload --port 8000
รัน (prod): uvicorn main:app --host 0.0.0.0 --port 8000

Endpoints:
  GET  /health
  GET  /api/data?tickers=A,B&period=3y   → yfinance proxy
  GET  /api/search?q=apple               → ticker autocomplete
  GET  /api/ports                        → list ports
  POST /api/ports                        → create port
  GET  /api/ports/{id}                   → get port
  PUT  /api/ports/{id}                   → update port
  DELETE /api/ports/{id}                 → delete port
  POST /api/ml-views                     → LSTM+SVR machine-generated views
"""
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from database import connect_db, close_db
from routers import market, search, ports, ml_views


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await connect_db()
    except Exception as e:
        # MongoDB is only needed for /api/ports (save/load portfolios).
        # ML views and market data still work without it.
        print(f"  ⚠️  MongoDB unavailable ({e}) — /api/ports disabled, ML views still work")
    yield
    try:
        await close_db()
    except Exception:
        pass


app = FastAPI(
    title="BL Optimizer API",
    version="2.0.0",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────
_origins = os.getenv("CORS_ORIGINS", "http://localhost:8770").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _origins],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────
app.include_router(market.router, prefix="/api", tags=["market"])
app.include_router(search.router, prefix="/api", tags=["search"])
app.include_router(ports.router,  prefix="/api", tags=["ports"])
app.include_router(ml_views.router, prefix="/api", tags=["ml-views"])


# ── Health check ──────────────────────────────────────────────────
@app.get("/health", tags=["health"])
async def health():
    return {"ok": True, "service": "bl-optimizer-backend"}
