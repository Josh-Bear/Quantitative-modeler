"""
CRUD endpoints for Ports.

GET    /api/ports          → list all (sorted by updated_at desc)
POST   /api/ports          → create
GET    /api/ports/{id}     → get by id
PUT    /api/ports/{id}     → update (partial — only provided fields are changed)
DELETE /api/ports/{id}     → delete
"""
from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, HTTPException

from database import get_db
from models import PortCreate, PortUpdate

router = APIRouter()


def _oid(port_id: str) -> ObjectId:
    """Parse string → ObjectId, raise 422 on bad format."""
    try:
        return ObjectId(port_id)
    except InvalidId:
        raise HTTPException(422, f"Invalid port id: {port_id!r}")


def _to_out(doc: dict) -> dict:
    """Convert MongoDB doc to JSON-serialisable dict."""
    doc = dict(doc)
    doc["id"] = str(doc.pop("_id"))
    return doc


# ── List ──────────────────────────────────────────────────────────

@router.get("/ports")
async def list_ports():
    db = get_db()
    docs = await db.ports.find().sort("updated_at", -1).to_list(length=200)
    return {"ok": True, "data": [_to_out(d) for d in docs]}


# ── Create ────────────────────────────────────────────────────────

@router.post("/ports", status_code=201)
async def create_port(body: PortCreate):
    db = get_db()
    now = datetime.now(timezone.utc)
    doc = {
        "name": body.name,
        "tickers": [t.strip().upper() for t in body.tickers],
        "last_run": None,
        "created_at": now,
        "updated_at": now,
    }
    result = await db.ports.insert_one(doc)
    created = await db.ports.find_one({"_id": result.inserted_id})
    return {"ok": True, "data": _to_out(created)}


# ── Read ──────────────────────────────────────────────────────────

@router.get("/ports/{port_id}")
async def get_port(port_id: str):
    db = get_db()
    doc = await db.ports.find_one({"_id": _oid(port_id)})
    if not doc:
        raise HTTPException(404, "port not found")
    return {"ok": True, "data": _to_out(doc)}


# ── Update (partial) ──────────────────────────────────────────────

@router.put("/ports/{port_id}")
async def update_port(port_id: str, body: PortUpdate):
    db = get_db()
    updates: dict = {}

    if body.name is not None:
        updates["name"] = body.name
    if body.tickers is not None:
        updates["tickers"] = [t.strip().upper() for t in body.tickers]
    if body.last_run is not None:
        updates["last_run"] = body.last_run

    if not updates:
        raise HTTPException(400, "no fields to update")

    updates["updated_at"] = datetime.now(timezone.utc)

    result = await db.ports.update_one({"_id": _oid(port_id)}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(404, "port not found")

    doc = await db.ports.find_one({"_id": _oid(port_id)})
    return {"ok": True, "data": _to_out(doc)}


# ── Delete ────────────────────────────────────────────────────────

@router.delete("/ports/{port_id}", status_code=204)
async def delete_port(port_id: str):
    db = get_db()
    result = await db.ports.delete_one({"_id": _oid(port_id)})
    if result.deleted_count == 0:
        raise HTTPException(404, "port not found")
    # 204 No Content — return nothing
