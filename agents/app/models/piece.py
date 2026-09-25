"""Piece work-state (domain model §1.9).

The Piece is an inherent **composite**: its *content* (draft.html / sources.md / transcript.md /
assets revisions) lives in **Git** (D4, handled by ``app.git``), while its *work-state* — stage,
ownership, links, cost, open GAP/clearance counts — lives here in **Mongo** (D3). This model is the
Mongo half only; ``latest_revision`` is a *pointer* (a Git ref/label), never the content.

Lifecycle: the SETTLED 9-state machine (§1.9, reproduced from the decisions report — do NOT
re-invent). The allowed transitions are encoded as data so the orchestration ticket can consult
them; enforcing *who* may trigger a human advance ("enough input" / "reviews done" / "finalize")
is that later ticket's job, not the data layer's.

Invariant: exactly one active Voice; voices never mix within a piece (structurally: a single
``voice`` field). Switching voice mid-piece is a deliberate, confirmed act upstream.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import Field

from app.models.common import MongoModel
from app.models.drive import DriveFileRef
from app.models.narrative import DistributionIntent
from app.models.review_round import DocRef


class PieceRole(str, Enum):
    anchor = "anchor"
    derivative = "derivative"


class PieceStage(str, Enum):
    interviewing = "interviewing"
    drafting = "drafting"
    council = "council"
    review = "review"
    incorporating = "incorporating"
    finalizing = "finalizing"
    finalized = "finalized"
    lessons = "lessons"
    paused = "paused"
    released = "released"

    @classmethod
    def _missing_(cls, value: object) -> PieceStage | None:
        # Legacy documents / callers used `published` for this same terminal ship state.
        # Coerce rather than fork the machine into two terminal values.
        if value == "published":
            return cls.released
        return None


# The settled transition table (§1.9 state diagram). Keys → the set of stages reachable next.
#
# `released` (HITL AuthorizeRelease, finalized → released) is the terminal *stage*. What actually
# shipped is a separate, repeatable, immutable numbered Publication Release (`app.models.publication`
# + `app.release`) — re-authorizing from `released` appends release N+1 without leaving the stage
# and without mutating release N. This replaces the conflicting terminal-`published` + republish
# comments that could not actually re-publish (the stage was terminal; the service required
# `finalized`). Two deliberate calls, unchanged in spirit from the v1 D13 reversal:
#
# - **Terminal stage, no outgoing edges.** A circulating public link cannot be un-shared, so the
#   stage must not imply the action is reversible. Additional releases are not a stage transition.
# - **Independent of the `lessons` gate, not sequenced with it.** `finalized` can still reach
#   `lessons` too, and the existing `lessons → finalized` loop is unchanged, so
#   `finalized → lessons → finalized → released` remains possible.
# - **The Content Project workspace is NOT terminal after release.** Authorizing a release never
#   flips `ContentProject.disposition` to completed — see `app/release/README.md`.
ALLOWED_TRANSITIONS: dict[PieceStage, frozenset[PieceStage]] = {
    PieceStage.interviewing: frozenset({PieceStage.drafting, PieceStage.paused}),
    PieceStage.drafting: frozenset({PieceStage.council, PieceStage.interviewing}),
    PieceStage.council: frozenset({PieceStage.review, PieceStage.interviewing}),
    PieceStage.review: frozenset(
        {
            PieceStage.incorporating,
            PieceStage.interviewing,
            PieceStage.finalizing,
            PieceStage.paused,
        }
    ),
    PieceStage.incorporating: frozenset({PieceStage.council, PieceStage.review}),
    PieceStage.finalizing: frozenset({PieceStage.finalized}),
    PieceStage.finalized: frozenset({PieceStage.lessons, PieceStage.released}),
    PieceStage.lessons: frozenset({PieceStage.finalized}),
    PieceStage.paused: frozenset({PieceStage.interviewing}),
    PieceStage.released: frozenset(),
}


def can_transition(src: PieceStage, dst: PieceStage) -> bool:
    """True if ``src → dst`` is a legal edge in the settled state machine (§1.9)."""
    return PieceStage(dst) in ALLOWED_TRANSITIONS[PieceStage(src)]


def is_released_stage(stage: PieceStage | str | None) -> bool:
    """True for the terminal ship state, including the legacy ``published`` wire value."""
    if stage is None:
        return False
    return PieceStage(stage) == PieceStage.released


class Piece(MongoModel):
    # New workflow identity. Existing pipeline records predate Content Projects; the clean-cut
    # workflow requires both values on every Piece it creates and never infers either from format.
    content_project_id: str | None = None
    role: PieceRole | None = None
    # Set when this Piece was *promoted* from a child derivative artifact of another piece
    # (cmw-lesson-lineage-impl). Child artifacts are NOT Pieces — they live on the anchor until
    # they need their own owner/review/publish state. `None` for anchors and pre-lineage pieces.
    parent_piece_id: str | None = None
    slug: str  # identity (from the origin spike headline); backed by this Mongo id
    voice: str  # mutable FK to a Voice slug — exactly one at a time (voices never mix)
    title: str | None = None
    origin_spike_id: str | None = None
    target: str | None = None  # blog / FAQ / LinkedIn…
    partners: list[str] = Field(default_factory=list)
    stage: PieceStage = PieceStage.interviewing

    # Attribution (never a permission gate — §1.17).
    owner: str | None = None  # User (email/id)
    assigned_experts: list[str] = Field(default_factory=list)

    # Pointers into the other stores (never the content itself).
    latest_revision: str | None = None  # Git ref/label of the latest committed revision
    latest_council_id: str | None = None  # structured Council result in Mongo
    current_review_round_id: str | None = None

    # The Git revision the current approval is for (stamped when entering `finalized`, or by
    # `accept-final-revision`). AuthorizeRelease refuses when `latest_revision` differs unless a
    # TrivialEditWaiver covers the pair — see `app.release.approval`.
    approved_revision: str | None = None
    approved_at: datetime | None = None

    # Mirrored editorial-block counts so the dashboard / "needs my action" predicate can query
    # without reading Git (§1.11 — canonical text stays in the Git editorial block).
    open_gaps: int = 0
    open_clearances: int = 0


    # Staleness triage (cmw-staleness-timestamps): `updated_at` (inherited from `MongoModel`)
    # already answers "when did anything last write this piece" — every batch job, cost charge,
    # and stage move already bumps it. That is a MACHINE signal: a job completing an hour ago
    # updates it even if no human has looked at the piece in weeks. `last_human_touch_at` is the
    # separate, deliberately narrower signal — set only by a person acting on the piece (a
    # `PieceMachine` human trigger, or answering/editing an interview turn — see
    # `app.orchestration.machine`/`app.interview.engine` for exactly which calls set it and why).
    # `None` means no human touch has been recorded yet (e.g. a piece still awaiting its first
    # interview answer).
    last_human_touch_at: datetime | None = None

    # Carried forward from the seeding Narrative/Spike (§5-Q5 deferred-distribution anchor).
    intent: DistributionIntent | None = None

    # Finalize outputs (D13, use case G/J; domain model §1.19): the final Google-Doc link + the
    # render provenance, so a re-render is reproducible and the UI can show "Open final Doc". The
    # branded HTML/PDF themselves are disposable/regenerable (§1.19) and are not recorded here.
    final_doc: DocRef | None = None
    final_template_version: str | None = None
    final_rendered_at: datetime | None = None

    # Per-piece Google Drive folder (cmw-drive-named-folder-scoping): every Google artifact this
    # piece produces — review-round Docs, the finalized Doc, and the branded HTML/PDF as ordinary
    # uploaded files — lands in the named My-Drive root's per-piece folder, so sharing that
    # folder gives a reviewer everything for the piece. `None` until GOOGLE_DRIVE_ROOT_FOLDER_NAME
    # is configured (see app/drive/README.md) and this piece has produced its first Google
    # artifact — created once, idempotently, and reused by
    # every later finalize/review-mint/publish (never a second folder for the same piece).
    drive_folder_id: str | None = None
    drive_folder_url: str | None = None
    # The `Published/` subfolder (holding publish's own re-rendered copies, Hendo's call — never
    # the finalize originals above, moved or re-parented). Same idempotent-by-pointer discipline.
    drive_published_folder_id: str | None = None

    # Finalize's branded HTML/PDF, uploaded as ordinary Drive files (real text/html /
    # application/pdf, never converted to a Google format) into `drive_folder_id`. The render
    # itself stays disposable/regenerable (§1.19) — only its Drive location is durable enough to
    # be worth recording, the same way `final_doc` records the Doc's location and nothing more.
    final_drive_html: DriveFileRef | None = None
    final_drive_pdf: DriveFileRef | None = None

    # Published's Drive-side copies, in `drive_published_folder_id` — parallel to
    # `published_html_url`/`published_pdf_url` in S3 below (both destinations are populated by the
    # same publish run; S3 is unaffected by this ticket).
    published_drive_html: DriveFileRef | None = None
    published_drive_pdf: DriveFileRef | None = None

    # Latest-release convenience pointers (HITL AuthorizeRelease from finalized/released; see
    # `app.release` and `app.models.publication.PublicationRelease`). The canonical history is the
    # immutable numbered Publication Release documents; these fields mirror the latest one so
    # existing UI keeps working. `published_release` is `0` until the first authorization.
    published_release: int = 0
    published_html_url: str | None = None
    published_pdf_url: str | None = None
    published_doc: DocRef | None = None
    published_at: datetime | None = None

    # Archive (triage at scale, orthogonal to the stage machine — deliberately NOT a PieceStage
    # value: it must be settable/reversible regardless of stage, including `released`, without
    # colliding with the stage rail/ALLOWED_TRANSITIONS/terminal-state semantics). Purely a
    # dashboard-visibility decision — `None` (never archived) otherwise changes nothing about the
    # piece: no job/permission/asset side effects. Reversible (unarchive sets it back to `None`),
    # per this project's "never delete anything" principle. Still reachable at its direct
    # `/api/pieces/{id}` URL either way — only the dashboard queue (`app.dashboard.build_queue`)
    # excludes an archived piece.
    archived_at: datetime | None = None

    # Provenance flag (cmw-brain-pieces-visibility): True when this Mongo record was minted by
    # the brain-draft sync (`app.brain_sync`) to complete the composite for a brain-authored
    # draft folder (`drafts/<slug>/` written by the brain, never through this pipeline — no
    # interview/council/revisions). Purely informational: it changes no behavior, and pieces the
    # pipeline created itself always carry the default False.
    brain_synced: bool = False
