"""Concrete work-state repositories (domain model §1, §3).

One repository per Mongo work-state entity. Each is a thin ``BaseRepository`` subclass plus the
domain queries the dashboard / "needs my action" predicate / orchestration seams will need. The
``WorkStateStore`` facade bundles them so callers get every collection off one database handle.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.models import (
    Council,
    DerivativeArtifact,
    FeedbackItem,
    FeedbackStatus,
    Interview,
    InterviewStatus,
    Job,
    JobStatus,
    Lesson,
    LessonStatus,
    Narrative,
    Piece,
    PieceStage,
    PublicationRelease,
    ReviewRound,
    Source,
    Spike,
    SpikeStatus,
    TrivialEditWaiver,
    User,
    can_transition,
)
from app.models.common import utcnow
from app.repositories.base import BaseRepository, mongo_encode


class UserRepository(BaseRepository[User]):
    model = User
    collection_name = "users"

    async def get_by_email(self, email: str) -> User | None:
        return await self.find_one({"email": email})


class SourceRepository(BaseRepository[Source]):
    model = Source
    collection_name = "sources"

    async def list_enabled(self) -> list[Source]:
        return await self.find({"enabled": True})

    async def by_kind(self, kind: Any) -> list[Source]:
        return await self.find({"kind": mongo_encode(kind)})


class NarrativeRepository(BaseRepository[Narrative]):
    model = Narrative
    collection_name = "narratives"

    async def by_author(self, author: str) -> list[Narrative]:
        return await self.find({"author": author})


class SpikeRepository(BaseRepository[Spike]):
    model = Spike
    collection_name = "spikes"

    async def vault(self) -> list[Spike]:
        """The Vault view (§1.7): spikes still in the pool — proposed or vaulted."""
        return await self.find(
            {"status": {"$in": [SpikeStatus.proposed.value, SpikeStatus.vaulted.value]}}
        )

    async def by_creator(self, creator: str) -> list[Spike]:
        return await self.find({"creator": creator})

    async def by_status(self, status: Any) -> list[Spike]:
        return await self.find({"status": mongo_encode(status)})


class JobRepository(BaseRepository[Job]):
    model = Job
    collection_name = "jobs"

    async def by_piece(self, piece_id: str) -> list[Job]:
        return await self.find({"piece_id": piece_id})

    async def by_status(self, status: Any) -> list[Job]:
        return await self.find({"status": mongo_encode(status)})

    async def by_type(self, type_: Any) -> list[Job]:
        return await self.find({"type": mongo_encode(type_)})

    async def by_piece_and_type(self, piece_id: str, type_: Any) -> list[Job]:
        return await self.find(
            {"piece_id": piece_id, "type": mongo_encode(type_)},
            sort=[("created_at", -1), ("_id", -1)],
        )

    async def claim(self, id: str) -> Job | None:
        """Atomically claim one queued job for execution.

        ``None`` means the job either vanished or another caller already claimed/settled it. Only
        the ``queued → running`` compare-and-set here may start an execution; callers must not
        emulate a claim with a read followed by :meth:`update`.
        """
        now = utcnow()
        result = await self.collection.update_one(
            {"_id": id, "status": JobStatus.queued.value},
            {
                "$set": {
                    "status": JobStatus.running.value,
                    "started_at": now,
                    "heartbeat_at": now,
                    "updated_at": now,
                }
            },
        )
        if result.modified_count != 1:
            return None
        return await self.get(id)

    async def reclaim(self, id: str) -> Job | None:
        """Atomically claim one failed/stuck job for an explicit retry execution."""
        now = utcnow()
        result = await self.collection.update_one(
            {
                "_id": id,
                "status": {"$in": [JobStatus.failed.value, JobStatus.stuck.value]},
            },
            {
                "$set": {
                    "status": JobStatus.running.value,
                    "attempts": 0,
                    "started_at": now,
                    "heartbeat_at": now,
                    "error": None,
                    "cost": 0.0,
                    "updated_at": now,
                }
            },
        )
        if result.modified_count != 1:
            return None
        return await self.get(id)


class PieceRepository(BaseRepository[Piece]):
    model = Piece
    collection_name = "pieces"

    async def by_slug(self, slug: str) -> Piece | None:
        return await self.find_one({"slug": slug})

    async def by_stage(self, stage: Any) -> list[Piece]:
        return await self.find({"stage": mongo_encode(stage)})

    async def transition(
        self, id: str, dst: PieceStage, *, expected: PieceStage | None = None
    ) -> Piece:
        """Advance a piece's stage, enforcing the settled state machine (§1.9).

        Raises ``ValueError`` on an illegal edge — the data layer refuses to persist a
        transition the domain model forbids. The *authority* to trigger a human advance is an
        orchestration concern layered on top of this. The write is a compare-and-set against
        ``expected`` (or the stage read here when omitted), so a concurrent move cannot be
        overwritten or treated as a second successful trigger.
        """
        piece = await self.get(id)
        if piece is None:
            raise KeyError(f"no piece {id!r}")
        current = PieceStage(expected) if expected is not None else PieceStage(piece.stage)
        dst = PieceStage(dst)
        if current != dst and not can_transition(current, dst):
            raise ValueError(f"illegal stage transition {current.value} → {dst.value} (§1.9)")
        result = await self.collection.update_one(
            {"_id": id, **_stage_match(current)},
            {"$set": {"stage": dst.value, "updated_at": utcnow()}},
        )
        if result.matched_count != 1:
            latest = await self.get(id)
            if latest is None:
                raise KeyError(f"no piece {id!r}")
            raise ValueError(
                f"piece {id!r} stage changed from expected {current.value} "
                f"to {PieceStage(latest.stage).value}"
            )
        updated = await self.get(id)
        assert updated is not None
        return updated


    async def archive(self, id: str) -> Piece:
        """Hide a piece from the dashboard queue, regardless of stage (triage at scale).

        Purely a visibility flag — orthogonal to the stage machine (never a ``PieceStage`` value,
        never routed through ``transition``), so it changes nothing else about the piece. Raises
        ``KeyError`` if the piece is missing.
        """
        piece = await self.get(id)
        if piece is None:
            raise KeyError(f"no piece {id!r}")
        updated = await self.update(id, {"archived_at": utcnow()})
        assert updated is not None
        return updated

    async def unarchive(self, id: str) -> Piece:
        """Reverse :meth:`archive` — this project never deletes anything, so archiving is always
        reversible. Idempotent: unarchiving an already-unarchived piece is a no-op. Raises
        ``KeyError`` if the piece is missing.
        """
        piece = await self.get(id)
        if piece is None:
            raise KeyError(f"no piece {id!r}")
        updated = await self.update(id, {"archived_at": None})
        assert updated is not None
        return updated

    async def mark_human_touch(self, id: str, *, when: datetime | None = None) -> Piece:
        """Stamp ``last_human_touch_at`` (cmw-staleness-timestamps) — the ONE place that field is
        ever written. Callers are exactly the human-attributable actions the machine/interview
        engine have identified (see their own call sites for the reasoning on what counts);
        nothing else should call this directly. Raises ``KeyError`` if the piece is missing.
        """
        piece = await self.get(id)
        if piece is None:
            raise KeyError(f"no piece {id!r}")
        updated = await self.update(id, {"last_human_touch_at": when or utcnow()})
        assert updated is not None
        return updated


class InterviewRepository(BaseRepository[Interview]):
    model = Interview
    collection_name = "interviews"

    async def by_piece(self, piece_id: str) -> list[Interview]:
        # Sorted by `_id` ascending — a hex ObjectId string sorts lexicographically the same as
        # its creation order, so this is a stable "round 1, round 2, ..." ordering rather than
        # relying on Mongo's unspecified natural order (a piece-detail UI concern: which Interview
        # is round N depends on this being deterministic).
        return await self.find({"piece_id": piece_id}, sort=[("_id", 1)])

    async def open_for_piece(self, piece_id: str) -> list[Interview]:
        return await self.find({"piece_id": piece_id, "status": InterviewStatus.open.value})


class ReviewRoundRepository(BaseRepository[ReviewRound]):
    model = ReviewRound
    collection_name = "review_rounds"

    async def by_piece(self, piece_id: str) -> list[ReviewRound]:
        return await self.find({"piece_id": piece_id}, sort=[("round_number", 1)])

    async def latest_for_piece(self, piece_id: str) -> ReviewRound | None:
        rounds = await self.find({"piece_id": piece_id}, sort=[("round_number", -1)], limit=1)
        return rounds[0] if rounds else None


class FeedbackRepository(BaseRepository[FeedbackItem]):
    model = FeedbackItem
    collection_name = "feedback_items"

    async def by_piece(self, piece_id: str) -> list[FeedbackItem]:
        return await self.find({"piece_id": piece_id})

    async def by_round(self, review_round_id: str) -> list[FeedbackItem]:
        return await self.find({"review_round_id": review_round_id})

    async def open_items(self, piece_id: str) -> list[FeedbackItem]:
        return await self.find({"piece_id": piece_id, "status": FeedbackStatus.open.value})


class CouncilRepository(BaseRepository[Council]):
    model = Council
    collection_name = "councils"

    async def by_piece(self, piece_id: str) -> list[Council]:
        return await self.find({"piece_id": piece_id}, sort=[("round_number", 1), ("iteration", 1)])

    async def latest_for_piece(self, piece_id: str) -> Council | None:
        results = await self.find(
            {"piece_id": piece_id}, sort=[("round_number", -1), ("iteration", -1)], limit=1
        )
        return results[0] if results else None


class LessonRepository(BaseRepository[Lesson]):
    model = Lesson
    collection_name = "lessons"

    async def proposed(self) -> list[Lesson]:
        """Pending proposals awaiting the D12 human gate (Mongo side of the store boundary)."""
        return await self.find({"status": LessonStatus.proposed.value})

    async def by_voice(self, voice: str) -> list[Lesson]:
        return await self.find({"voice": voice})

    async def by_piece(self, piece_id: str) -> list[Lesson]:
        return await self.find({"source_piece_id": piece_id})


class DerivativeRepository(BaseRepository[DerivativeArtifact]):
    model = DerivativeArtifact
    collection_name = "derivative_artifacts"

    async def by_anchor(self, anchor_piece_id: str) -> list[DerivativeArtifact]:
        return await self.find({"anchor_piece_id": anchor_piece_id})

    async def by_anchor_and_destination(
        self, anchor_piece_id: str, destination: str
    ) -> DerivativeArtifact | None:
        return await self.find_one(
            {"anchor_piece_id": anchor_piece_id, "destination": destination}
        )


class PublicationReleaseRepository(BaseRepository[PublicationRelease]):
    """Insert-only. Publication Releases are immutable numbered records."""

    model = PublicationRelease
    collection_name = "publication_releases"

    async def by_piece(self, piece_id: str) -> list[PublicationRelease]:
        return await self.find({"piece_id": piece_id}, sort=[("release_number", 1)])

    async def latest_for_piece(self, piece_id: str) -> PublicationRelease | None:
        results = await self.find(
            {"piece_id": piece_id}, sort=[("release_number", -1)], limit=1
        )
        return results[0] if results else None

    async def next_number(self, piece_id: str) -> int:
        latest = await self.latest_for_piece(piece_id)
        return (latest.release_number + 1) if latest else 1

    async def update(self, id: str, changes: dict[str, Any]) -> PublicationRelease | None:
        raise RuntimeError("Publication Releases are immutable; mint a new numbered release instead")


class TrivialEditWaiverRepository(BaseRepository[TrivialEditWaiver]):
    model = TrivialEditWaiver
    collection_name = "trivial_edit_waivers"

    async def by_piece(self, piece_id: str) -> list[TrivialEditWaiver]:
        return await self.find({"piece_id": piece_id}, sort=[("recorded_at", 1)])


def _stage_match(stage: PieceStage) -> dict[str, object]:
    """Compare-and-set filter for a piece stage, treating legacy ``published`` as ``released``."""
    if stage == PieceStage.released:
        return {"stage": {"$in": ["released", "published"]}}
    return {"stage": stage.value}


class WorkStateStore:
    """Facade bundling every work-state repository off one database handle."""

    def __init__(self, database: Any) -> None:
        self.database = database
        self.users = UserRepository(database)
        self.sources = SourceRepository(database)
        self.narratives = NarrativeRepository(database)
        self.spikes = SpikeRepository(database)
        self.jobs = JobRepository(database)
        self.pieces = PieceRepository(database)
        self.interviews = InterviewRepository(database)
        self.review_rounds = ReviewRoundRepository(database)
        self.feedback = FeedbackRepository(database)
        self.councils = CouncilRepository(database)
        self.lessons = LessonRepository(database)
        self.derivatives = DerivativeRepository(database)
        self.releases = PublicationReleaseRepository(database)
        self.trivial_edit_waivers = TrivialEditWaiverRepository(database)
