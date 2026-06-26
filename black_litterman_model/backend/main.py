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
"""
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from database import connect_db, close_db
from routers import market, search, ports


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_db()
    yield
    await close_db()


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


# ── Health check ──────────────────────────────────────────────────
@app.get("/health", tags=["health"])
async def health():
    return {"ok": True, "service": "bl-optimizer-backend"}
