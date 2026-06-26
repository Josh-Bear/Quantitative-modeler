"""
MongoDB connection via Motor (async driver).
Call connect_db() on startup, close_db() on shutdown.
"""
import os
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

load_dotenv()

MONGODB_URL: str = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
MONGODB_DB: str = os.getenv("MONGODB_DB", "bl_optimizer")

_client: AsyncIOMotorClient | None = None


def get_db() -> AsyncIOMotorDatabase:
    """Return the active database handle (call after connect_db)."""
    if _client is None:
        raise RuntimeError("Database not connected — call connect_db() first")
    return _client[MONGODB_DB]


async def connect_db() -> None:
    global _client
    _client = AsyncIOMotorClient(MONGODB_URL)
    # Create index on ports collection (idempotent)
    db = _client[MONGODB_DB]
    await db.ports.create_index("updated_at")
    print(f"  ✅  MongoDB connected → {MONGODB_URL} / {MONGODB_DB}")


async def close_db() -> None:
    global _client
    if _client:
        _client.close()
        _client = None
