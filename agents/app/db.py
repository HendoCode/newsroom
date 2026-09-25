"""MongoDB connection wiring for the work-state layer (D3, §6, §7).

The single MongoDB instance (Atlas in prod; the compose ``mongo`` service locally) backs the
work-state collections. The connection string is read **server-side only** from ``Settings``
(never client-exposed, D14). The parallel-isolated-instances contract holds unchanged: each
compose instance points ``MONGO_URL`` at its own ephemeral tmpfs mongo over the internal network.

The repository layer (``app.repositories``) is driver-agnostic: it takes an
``AsyncIOMotorDatabase``-shaped object, so the same code runs against motor in production and the
in-memory ``mongomock-motor`` double in tests.
"""

from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo.errors import ConfigurationError

from app.config import Settings, get_settings


def create_client(settings: Settings | None = None) -> AsyncIOMotorClient:
    """Create a motor client from server-side settings. Caller owns closing it."""
    settings = settings or get_settings()
    if not settings.mongo_url:
        raise RuntimeError(
            "MONGO_URL is not configured; the work-state layer needs a MongoDB connection (D3)."
        )
    return AsyncIOMotorClient(settings.mongo_url)


def get_database(
    client: AsyncIOMotorClient, settings: Settings | None = None
) -> AsyncIOMotorDatabase:
    """Return the logical work-state database.

    If the connection string already names a default database (as the compose URL does:
    ``mongodb://mongo:27017/content_machine``), honor it; otherwise fall back to
    ``settings.mongo_db_name``.
    """
    settings = settings or get_settings()
    try:
        default = client.get_default_database()
    except ConfigurationError:  # no default db named in the URI — use the configured name
        default = None
    if default is not None:
        return default
    return client[settings.mongo_db_name]
