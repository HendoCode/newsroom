"""Piece-detail read-model (cmw-ui-wireframes §4 screen 2): one piece, its whole lifecycle.

Assembles a single :class:`~app.schemas.PieceDetailResponse` by joining the piece's work-state
(Mongo) against the structured Council/ReviewRound/Interview/Lesson/Job records that belong to it,
plus the semantic ``draft.html`` (editorial block included — this screen is where GAPs/clearances
are meant to be seen; only external-share/finalize strip them) read through the Git content store.

Mirrors ``app.dashboard``'s shape deliberately: :func:`find_piece_collections` filters the same
:class:`~app.dashboard.WorkStateCollections` the dashboard already loads (real store or seed) down
to one piece, so both read-models share one join style and one seed dataset — a piece card's link
target always resolves here, whether backed by real Mongo or the walking-skeleton seed.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.dashboard import WorkStateCollections, job_failure_ref
from app.evidence import build_piece_evidence
from app.git.content import GitContentStore, PieceFiles
from app.models import (
    MANDATORY_EDITORS,
    Council,
    DocRef,
    DriveFileRef,
    Interview,
    InterviewStatus,
    Job,
    JobStatus,
    Lesson,
    Piece,
    ReviewRound,
    ReviewRoundStatus,
    ShareMode,
)
from app.piece_md import markdown_to_html, piece_md_content_section
from app.schemas import (
    ActivityEntry,
    CouncilOut,
    DocRefOut,
    DriveFileRefOut,
    EditorScoreOut,
    InterviewOut,
    LessonOut,
    PieceDetailResponse,
    ReviewRoundOut,
)

_OPEN_FAILURE_STATUSES = frozenset({JobStatus.failed, JobStatus.stuck})
_RUNNING_STATUSES = frozenset({JobStatus.queued, JobStatus.running})


@dataclass
class PieceCollections:
    """The work-state collections joined against one piece."""

    piece: Piece
    interviews: list[Interview]
    jobs: list[Job]
    councils: list[Council]
    review_rounds: list[ReviewRound]
    lessons: list[Lesson]


def find_piece_collections(work: WorkStateCollections, piece_id: str) -> PieceCollections | None:
    """Filter the whole-queue collections down to one piece, or ``None`` if it isn't in there."""
    piece = next((p for p in work.pieces if p.id == piece_id), None)
    if piece is None:
        return None
    pid = piece.id
    return PieceCollections(
        piece=piece,
        interviews=[i for i in work.interviews if i.piece_id == pid],
        jobs=[j for j in work.jobs if j.piece_id == pid],
        councils=[c for c in work.councils if c.piece_id == pid],
        review_rounds=[r for r in work.review_rounds if r.piece_id == pid],
        lessons=[l for l in work.lessons if l.source_piece_id == pid],
    )


def draft_content_from_files(files: PieceFiles | None) -> str | None:
    """The readable content for one piece's already-loaded ``PieceFiles``: the semantic
    ``draft.html`` master when one exists, and — for brain-authored DIRECT-AUTHORED pieces that
    carry their content in ``piece.md`` after the ``---`` divider instead of a ``draft.html``
    (the 2026-08-31 AWS×Hendo seller briefs; see ``app.piece_md``) — that markdown section
    rendered to HTML instead. ``None`` when the files are unavailable or the piece has no
    content yet (metadata-only ``piece.md``, no revision).

    The fallback can only fire on brain-authored files: the webapp never writes ``piece.md``
    itself, so a pipeline piece without a revision keeps its honest "no revision yet" state.
    """
    if files is None:
        return None
    if files.draft_html is not None:
        return files.draft_html
    section = piece_md_content_section(files.piece_md)
    if section is None:
        return None
    return markdown_to_html(section)


def read_draft_content(content: GitContentStore | None, slug: str) -> str | None:
    """The readable content for ``slug`` — thin convenience over :func:`draft_content_from_files`
    for callers that only have the store + slug and don't need the rest of the piece's files
    (callers that also need ``sources.md`` for the evidence trail read the files once themselves
    via ``GitContentStore.read_piece_files`` rather than reading them twice)."""
    if content is None:
        return None
    return draft_content_from_files(content.read_piece_files(slug))


def _latest_council(councils: list[Council]) -> Council | None:
    return max(councils, key=lambda c: (c.round_number, c.iteration)) if councils else None


def _latest_review_round(rounds: list[ReviewRound]) -> ReviewRound | None:
    return max(rounds, key=lambda r: r.round_number) if rounds else None


def _council_out(council: Council) -> CouncilOut:
    return CouncilOut(
        round_number=council.round_number,
        iteration=council.iteration,
        revision=council.revision,
        aggregate=council.aggregate,
        cost=council.cost,
        stop_reason=council.stop_reason,
        stop_message=council.stop_message,
        editor_scores=[
            EditorScoreOut(
                editor=s.editor,
                score=s.score,
                mandatory=s.editor in MANDATORY_EDITORS,
                editorial_fixes=list(s.editorial_fixes),
                information_gaps=list(s.information_gaps),
                clearances=list(s.clearances),
                hard_cap_applied=s.hard_cap_applied,
            )
            for s in council.editor_scores
        ],
    )


def _review_round_out(round_: ReviewRound) -> ReviewRoundOut:
    return ReviewRoundOut(
        round_number=round_.round_number,
        minted_from_revision=round_.minted_from_revision,
        status=ReviewRoundStatus(round_.status).value,
        share_mode=ShareMode(round_.doc.share_mode).value,
        doc_url=round_.doc.url,
        opened_at=round_.opened_at,
        routing_log=list(round_.routing_log),
    )


def _interview_out(iv: Interview) -> InterviewOut:
    return InterviewOut(
        interview_id=iv.id or "",
        assigned_expert=iv.assigned_expert,
        status=InterviewStatus(iv.status).value,
        about=iv.about,
        is_gap_interview=iv.is_gap_interview,
    )


def _lesson_out(lesson: Lesson) -> LessonOut:
    return LessonOut(
        id=lesson.id or "",
        voice=lesson.voice,
        source_piece_id=lesson.source_piece_id,
        observed_change=lesson.observed_change,
        generalizable_rule=lesson.generalizable_rule,
        status=lesson.status if isinstance(lesson.status, str) else lesson.status.value,
    )


# --- activity/routing log ------------------------------------------------------------------
#
# There is no stored "activity" entity in the domain model (cmw-domain-model report §1) — the
# wireframe's log is a narrative view over records that already exist. We synthesize it from the
# same joined collections rather than inventing a new store: one entry per finished job, per
# council pass, per review-round open/close, per completed interview.


def _job_entries(jobs: list[Job]) -> list[ActivityEntry]:
    entries: list[ActivityEntry] = []
    for job in jobs:
        status = JobStatus(job.status)
        if status in _RUNNING_STATUSES:
            job_type = job.type if isinstance(job.type, str) else job.type.value
            entries.append(
                ActivityEntry(
                    label=f"{job_type} job {status.value}",
                    detail=None,
                    at=job.started_at or job.created_at,
                )
            )
            continue
        if status not in (JobStatus.succeeded, *_OPEN_FAILURE_STATUSES):
            continue
        job_type = job.type if isinstance(job.type, str) else job.type.value
        label = f"{job_type} job ok" if status == JobStatus.succeeded else f"{job_type} job {status.value}"
        detail = f"{job.error.code}: {job.error.message}" if job.error else None
        entries.append(
            ActivityEntry(label=label, detail=detail, at=job.heartbeat_at or job.started_at)
        )
    return entries


def _council_entries(councils: list[Council]) -> list[ActivityEntry]:
    return [
        ActivityEntry(
            label=f"council pass · round {c.round_number}",
            detail=f"aggregate {c.aggregate:.1f}" if c.aggregate is not None else None,
            at=c.updated_at,
        )
        for c in councils
    ]


def _review_round_entries(rounds: list[ReviewRound]) -> list[ActivityEntry]:
    entries: list[ActivityEntry] = []
    for r in rounds:
        entries.append(
            ActivityEntry(
                label=f"round {r.round_number} opened",
                detail=f"minted from {r.minted_from_revision}",
                at=r.opened_at,
            )
        )
        status = ReviewRoundStatus(r.status)
        if status != ReviewRoundStatus.open:
            entries.append(
                ActivityEntry(label=f"round {r.round_number} {status.value}", at=r.updated_at)
            )
    return entries


def _interview_entries(interviews: list[Interview]) -> list[ActivityEntry]:
    return [
        ActivityEntry(label="interview marked complete", detail=iv.about, at=iv.updated_at)
        for iv in interviews
        if InterviewStatus(iv.status) == InterviewStatus.complete
    ]


def build_activity_log(collections: PieceCollections) -> list[ActivityEntry]:
    """The activity/routing log, newest first (undated entries sort last, never dropped)."""
    entries = [
        *_job_entries(collections.jobs),
        *_council_entries(collections.councils),
        *_review_round_entries(collections.review_rounds),
        *_interview_entries(collections.interviews),
    ]
    dated = sorted((e for e in entries if e.at is not None), key=lambda e: e.at, reverse=True)
    undated = [e for e in entries if e.at is None]
    return dated + undated


def build_piece_detail(
    collections: PieceCollections,
    draft_html: str | None,
    sources_md: str | None = None,
    *,
    seeded: bool = False,
) -> PieceDetailResponse:
    piece = collections.piece
    council = _latest_council(collections.councils)
    round_ = _latest_review_round(collections.review_rounds)
    failures = [
        job_failure_ref(j)
        for j in collections.jobs
        if JobStatus(j.status) in _OPEN_FAILURE_STATUSES
    ]
    evidence = build_piece_evidence(draft_html, sources_md)
    return PieceDetailResponse(
        id=piece.id or "",
        slug=piece.slug,
        title=piece.title or piece.slug,
        seeded=seeded,
        voice=piece.voice,
        stage=piece.stage if isinstance(piece.stage, str) else piece.stage.value,
        owner=piece.owner,
        assigned_experts=list(piece.assigned_experts),
        origin_spike_id=piece.origin_spike_id,
        target=piece.target,
        partners=list(piece.partners),
        open_gaps=piece.open_gaps,
        open_clearances=piece.open_clearances,

        latest_revision=piece.latest_revision or (council.revision if council else None),
        created_at=piece.created_at,
        updated_at=piece.updated_at,
        last_human_touch_at=piece.last_human_touch_at,
        draft_html=draft_html,
        brain_synced=piece.brain_synced,
        council=_council_out(council) if council else None,
        review_round=_review_round_out(round_) if round_ else None,
        review_rounds=[
            _review_round_out(r)
            for r in sorted(collections.review_rounds, key=lambda r: r.round_number)
        ],
        interviews=[_interview_out(i) for i in collections.interviews],
        failures=failures,
        lessons=[_lesson_out(l) for l in collections.lessons],
        activity=build_activity_log(collections),
        evidence_sources=evidence.sources,
        evidence_citations=evidence.citations,
        final_doc=_final_doc_out(piece),
        final_template_version=piece.final_template_version,
        final_rendered_at=piece.final_rendered_at,
        drive_folder_url=piece.drive_folder_url,
        final_drive_html=_drive_file_ref_out(piece.final_drive_html),
        final_drive_pdf=_drive_file_ref_out(piece.final_drive_pdf),
        published_release=piece.published_release,
        published_html_url=piece.published_html_url,
        published_pdf_url=piece.published_pdf_url,
        published_doc=_doc_ref_out(piece.published_doc),
        published_at=piece.published_at,
        published_drive_html=_drive_file_ref_out(piece.published_drive_html),
        published_drive_pdf=_drive_file_ref_out(piece.published_drive_pdf),
        archived_at=piece.archived_at,
        parent_piece_id=piece.parent_piece_id,
        role=piece.role if piece.role is None or isinstance(piece.role, str) else piece.role.value,
    )


def _final_doc_out(piece: Piece) -> DocRefOut | None:
    return _doc_ref_out(piece.final_doc)


def _doc_ref_out(doc: DocRef | None) -> DocRefOut | None:
    if doc is None:
        return None
    return DocRefOut(
        doc_id=doc.doc_id,
        url=doc.url,
        # DocRef is a plain nested BaseModel (not a MongoModel), so it doesn't inherit the
        # `use_enum_values` coercion — normalize explicitly (mirrors review/routes.py's mint response).
        share_mode=ShareMode(doc.share_mode).value,
    )


def _drive_file_ref_out(ref: DriveFileRef | None) -> DriveFileRefOut | None:
    if ref is None:
        return None
    return DriveFileRefOut(file_id=ref.file_id, url=ref.url)
