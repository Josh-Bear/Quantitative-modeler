"""
POST /api/ml-views — LSTM+SVR machine-generated BL views.
(docs/ML_VIEWS_DESIGN.md ส่วนที่ 2 — implemented as a FastAPI router because the
frontend talks to the FastAPI backend on :8000, not the legacy server.py.)
"""
import asyncio
from functools import partial

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import ml_constants as C

router = APIRouter()


class MLViewsRequest(BaseModel):
    tickers: list[str]
    tau: float = Field(C.BL_TAU, gt=0)
    delta: float = Field(C.BL_DELTA, gt=0)
    epochs: int = Field(C.LSTM_EPOCHS, ge=1, le=500)


@router.post("/ml-views")
async def ml_views(req: MLViewsRequest):
    tickers = [t.strip().upper() for t in req.tickers if t.strip()]
    if not tickers:
        raise HTTPException(400, "tickers required (non-empty list)")

    # Fail fast with an actionable message if the ML stack is missing
    try:
        import torch      # noqa: F401
        import sklearn    # noqa: F401
    except ImportError:
        raise HTTPException(
            500, "torch and scikit-learn required: pip install torch scikit-learn pandas")

    from ml_views import generate_ml_views

    print(f"  🤖 ML views for {tickers} (tau={req.tau}, epochs={req.epochs}) ...")

    # Training is synchronous + CPU-bound → offload so the event loop stays free
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None, partial(generate_ml_views, tickers,
                      tau=req.tau, delta=req.delta, epochs=req.epochs))

    if not result.get("ok"):
        raise HTTPException(500, result.get("error", "ML view generation failed"))
    return {"ok": True, "data": result}


@router.get("/ml-views/progress")
async def ml_views_progress():
    from ml_views import get_progress
    return {"ok": True, "data": get_progress()}
