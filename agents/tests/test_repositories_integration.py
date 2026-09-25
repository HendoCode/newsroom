"""Opt-in integration test against a REAL MongoDB (the compose ``mongo`` or any ``MONGO_URL``).

Skips cleanly when no server is reachable, so the default suite stays green with no dependencies.
Run it against the local stack with, e.g.::

    MONGO_URL=mongodb://127.0.0.1:27017 pytest tests/test_repositories_integration.py

It proves the same repository code that the in-memory suite exercises also round-trips through
the real motor driver (the parallel-isolated compose mongo included).
"""

from __future__ import annotations

import os

import pytest
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import PyMongoError

from app import models as m
from app.models.common import new_id
from app.repositories import WorkStateStore

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://127.0.0.1:27017")


async def _reachable(client: AsyncIOMotorClient) -> bool:
    try:
        await client.admin.command("ping")
        return True
    except PyMongoError:
        return False


async def test_real_mongo_roundtrip() -> None:
    client = AsyncIOMotorClient(MONGO_URL, serverSelectionTimeoutMS=800)
    if not await _reachable(client):
        client.close()
        pytest.skip(f"no MongoDB reachable at {MONGO_URL}")

    db_name = f"cmw_test_{new_id()}"  # unique db so parallel instances never collide
    db = client[db_name]
    try:
        store = WorkStateStore(db)
        piece = await store.pieces.insert(m.Piece(slug="integration", voice="demo-mira"))
        piece = await store.pieces.transition(piece.id, m.PieceStage.drafting)
        assert piece.stage == m.PieceStage.drafting

        fetched = await store.pieces.by_slug("integration")
        assert fetched is not None and fetched.stage == m.PieceStage.drafting

        await store.jobs.insert(m.Job(type=m.JobType.oracle, triggered_by="a@b"))
        assert len(await store.jobs.by_type(m.JobType.oracle)) == 1
    finally:
        await client.drop_database(db_name)
        client.close()
