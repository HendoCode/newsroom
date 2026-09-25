"""User / Identity (domain model §1.17).

A signed-in employee. Sign-in is Google Workspace SSO (NextAuth, D10) — the *provider* is
external; this durable record + its attribution edges are the Mongo work-state.

Invariant: authorization is **flat**. Role labels are informational only — they power
attribution and the "needs my action" filter, they never gate permissions (§1.17, D10).
"""

from __future__ import annotations

from enum import Enum

from pydantic import Field

from app.models.common import MongoModel


class RoleLabel(str, Enum):
    """Informational labels only — never a permission gate (§1.17)."""

    source_curator = "source-curator"
    author = "author"  # a.k.a. voice-contributor
    coordinator = "coordinator"
    interviewee = "interviewee"  # a.k.a. expert


class User(MongoModel):
    # Identity key = Google Workspace email. Backed by this Mongo record for continuity.
    email: str
    display_name: str | None = None
    role_labels: list[RoleLabel] = Field(default_factory=list)
