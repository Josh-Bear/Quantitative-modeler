"""
Pydantic schemas for request bodies and API responses.
MongoDB documents use ObjectId (_id); we expose it as a plain string `id`.
"""
from __future__ import annotations
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ── Request bodies ────────────────────────────────────────────────

class PortCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    tickers: list[str] = Field(default_factory=list)


class PortUpdate(BaseModel):
    """All fields optional — PATCH semantics."""
    name: str | None = Field(None, min_length=1, max_length=100)
    tickers: list[str] | None = None
    last_run: dict[str, Any] | None = None   # weights, metrics, views, params


# ── Response body ─────────────────────────────────────────────────

class PortOut(BaseModel):
    id: str
    name: str
    tickers: list[str]
    last_run: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime
