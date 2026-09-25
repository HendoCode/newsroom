"""Shared building blocks for the Mongo work-state models.

Every work-state entity in the domain model (§1, §3 of the cmw domain model report) is a Mongo
document. We keep the Python side driver-agnostic: `_id` is stored as a *string* (a hex ObjectId
generated on insert) rather than a BSON ``ObjectId`` object, so the same models round-trip
identically through the real motor driver and the in-memory test double, with no custom BSON
serialization. Timestamps are timezone-aware UTC.
"""

from __future__ import annotations

from datetime import UTC, datetime

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field


def new_id() -> str:
    """A fresh document id. Real ObjectId hex (monotonic-ish, index-friendly) held as a str."""
    return str(ObjectId())


def utcnow() -> datetime:
    """Current UTC instant as a **naive** datetime.

    MongoDB stores datetimes as UTC and returns them naive (no tzinfo). We mint naive-UTC
    timestamps so a value compares equal to itself after a store round-trip — mixing aware
    (on write) and naive (on read) datetimes raises ``TypeError`` on comparison.
    """
    return datetime.now(UTC).replace(tzinfo=None)


class MongoModel(BaseModel):
    """Base for every Mongo work-state document.

    - ``id`` maps to Mongo's ``_id`` (populate by field name *or* alias).
    - Enums are stored by value so documents are plain strings in the database.
    - Unknown fields are ignored on read, so a document written by a newer service version does
      not blow up an older reader (forward-compatible).
    """

    model_config = ConfigDict(
        populate_by_name=True,
        use_enum_values=True,
        # Validate defaults too, so a default enum is stored as its plain string value (not the
        # enum member) — otherwise defaulted vs explicitly-set fields would serialize differently.
        validate_default=True,
        extra="ignore",
        ser_json_by_alias=True,
    )

    id: str | None = Field(default=None, alias="_id")
    created_at: datetime | None = None
    updated_at: datetime | None = None
