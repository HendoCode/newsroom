"""Generic async Mongo repository (domain model §3 work-state store).

One thin, typed CRUD layer shared by every work-state collection. Concrete repositories subclass
it, set ``model`` + ``collection_name``, and add domain queries. The layer is driver-agnostic —
it only uses the standard motor/pymongo collection surface, so it runs identically against a real
MongoDB and the in-memory test double.

Conventions:
- ``_id`` is a string (see ``app.models.common``); ``insert`` generates one when absent.
- ``created_at``/``updated_at`` are managed here so callers never have to.
- Enums and nested Pydantic models are encoded to plain values before they hit Mongo.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel

from app.models.common import MongoModel, new_id, utcnow


def mongo_encode(value: Any) -> Any:
    """Recursively encode a Python value into Mongo-storable primitives.

    Enums → their value, Pydantic models → alias-keyed dicts, containers → encoded element-wise.
    Everything else (str/int/float/bool/datetime/None) passes through unchanged.
    """
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, BaseModel):
        return value.model_dump(by_alias=True)
    if isinstance(value, dict):
        return {k: mongo_encode(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [mongo_encode(v) for v in value]
    return value


class BaseRepository[T: MongoModel]:
    model: type[T]
    collection_name: str

    def __init__(self, database: Any) -> None:
        self.db = database
        self.collection = database[self.collection_name]

    # --- writes ---------------------------------------------------------------------------

    async def insert(self, obj: T) -> T:
        """Insert ``obj``, assigning ``_id`` and timestamps if unset. Returns the stored model."""
        now = utcnow()
        if obj.id is None:
            obj.id = new_id()
        if obj.created_at is None:
            obj.created_at = now
        obj.updated_at = now
        doc = obj.model_dump(by_alias=True)
        await self.collection.insert_one(doc)
        return obj

    async def update(self, id: str, changes: dict[str, Any]) -> T | None:
        """Apply a partial ``$set`` (plus a fresh ``updated_at``) and return the updated model."""
        payload = {mongo_encode_key(k): mongo_encode(v) for k, v in changes.items()}
        payload["updated_at"] = utcnow()
        await self.collection.update_one({"_id": id}, {"$set": payload})
        return await self.get(id)

    async def replace(self, obj: T) -> T:
        """Full replace of an existing document by id (upsert-free)."""
        if obj.id is None:
            raise ValueError("replace requires an id")
        obj.updated_at = utcnow()
        await self.collection.replace_one({"_id": obj.id}, obj.model_dump(by_alias=True))
        return obj

    async def delete(self, id: str) -> bool:
        result = await self.collection.delete_one({"_id": id})
        return result.deleted_count == 1

    # --- reads ----------------------------------------------------------------------------

    async def get(self, id: str) -> T | None:
        doc = await self.collection.find_one({"_id": id})
        return self.model.model_validate(doc) if doc else None

    async def find_one(self, query: dict[str, Any]) -> T | None:
        doc = await self.collection.find_one(query)
        return self.model.model_validate(doc) if doc else None

    async def find(
        self,
        query: dict[str, Any] | None = None,
        *,
        sort: list[tuple[str, int]] | None = None,
        limit: int = 0,
    ) -> list[T]:
        cursor = self.collection.find(query or {})
        if sort:
            cursor = cursor.sort(sort)
        if limit:
            cursor = cursor.limit(limit)
        return [self.model.model_validate(doc) async for doc in cursor]

    async def count(self, query: dict[str, Any] | None = None) -> int:
        return await self.collection.count_documents(query or {})


def mongo_encode_key(key: str) -> str:
    """Map a model field name to its stored key (only ``id`` differs → ``_id``)."""
    return "_id" if key == "id" else key
