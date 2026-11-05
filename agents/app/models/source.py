"""Source registry entry (domain model §1.3 — the settled Item-6 schema).

One *place* raw material comes from, held as a registry document. Distinct from the material
itself (that is the content-lake item, a separate downstream ticket). Kinds: gdrive, slack,
web-rss, linkedin-x-clip.

Invariants enforced here:
- Credentials are **server-side only, never in the registry doc** (D14). We reject any
  credential-looking key in ``config`` so a secret cannot be persisted by accident.
- ``linkedin-x-clip`` is always ``read-as-needed`` — credential-free, no scraper (D8).
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import Field, field_validator, model_validator

from app.models.common import MongoModel

# Keys that must never appear in a registry ``config`` blob — credentials live server-side.
_FORBIDDEN_CONFIG_KEY_TOKENS = ("key", "token", "secret", "password", "credential", "auth")


class SourceKind(str, Enum):
    gdrive = "gdrive"
    slack = "slack"
    web_rss = "web-rss"
    linkedin_x_clip = "linkedin-x-clip"


class SourceClassification(str, Enum):
    # The §4A key distinction: harvested on refresh vs pulled only when a run needs it.
    scraped_periodically = "scraped-periodically"
    read_as_needed = "read-as-needed"


class Source(MongoModel):
    display_name: str
    kind: SourceKind
    classification: SourceClassification
    enabled: bool = True
    lookback_default_days: int = 7  # per-run window (D7)
    config: dict[str, Any] = Field(default_factory=dict)  # kind-specific, NO credentials
    owner: str | None = None  # attribution (user email/id)
    last_refreshed: datetime | None = None
    per_source_metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("config")
    @classmethod
    def _no_credentials_in_config(cls, value: dict[str, Any]) -> dict[str, Any]:
        for key in value:
            lowered = key.lower()
            if any(token in lowered for token in _FORBIDDEN_CONFIG_KEY_TOKENS):
                raise ValueError(
                    f"credential-looking key {key!r} is forbidden in a Source config; "
                    "credentials are server-side only and never stored in the registry (D14)"
                )
        return value

    @model_validator(mode="after")
    def _linkedin_is_read_as_needed(self) -> Source:
        if (
            self.kind == SourceKind.linkedin_x_clip
            and self.classification != SourceClassification.read_as_needed
        ):
            raise ValueError(
                "linkedin-x-clip is always read-as-needed (credential-free, no scraper) — D8"
            )
        return self
