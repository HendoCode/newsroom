"""Pydantic response models for the agents service.

These are the wire contracts the Next.js BFF depends on. Keep them small and explicit;
downstream tickets add the domain models (pieces, spikes, sources, etc.).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


class BrainStatusResponse(BaseModel):
    """Provenance for the on-disk brain clone (D1/D2) — "which brain am I running," and whether a
    configured brain is actually reachable. ``connected`` is False whenever
    ``app.state.git_brain`` is ``None`` (brain_root isn't a usable git repo) — every provenance
    field is then null rather than guessed at. ``connected: false`` alone can't distinguish "no
    brain configured" from "configured but broken," which is exactly the bug this pair of fields
    fixes: ``configured`` is True once ``BRAIN_REPO_URL`` is set (an attempt was expected this
    boot), and ``error`` carries the real underlying clone/fetch failure message when that
    attempt (or the subsequent local open) failed — ``None`` when nothing failed. No secrets:
    ``remote_url`` is the clone's remote, never a token, and ``error`` is a git/SSH error string
    that never contains key material."""

    connected: bool
    configured: bool = False
    error: str | None = None
    root: str | None = None
    remote_url: str | None = None
    commit_sha: str | None = None
    commit_date: str | None = None
    commit_message: str | None = None


class BrainPullResponse(BaseModel):
    """Result of a successful on-demand ``POST /api/brain/pull`` — refresh the running clone from
    its remote without restarting the process. ``pulled`` is False for the one non-error no-op
    shape: no remote is configured at all (the self-managed local-dev clone — nothing to pull
    from); it's True whenever the fast-forward ran, whether or not it actually moved (already at
    the remote's tip counts as a successful pull). A real failure (unreachable remote, stale
    credential, diverged history) raises an HTTP error instead of returning this body — see the
    route docstring — since this is an action trigger an ops caller may check only the status of."""

    pulled: bool
    remote_url: str | None = None
    commit_sha: str | None = None
    commit_date: str | None = None
    commit_message: str | None = None


class StatusResponse(BaseModel):
    """Stub the BFF calls to prove end-to-end connectivity and to expose readiness of the
    seams downstream tickets will fill in. No secrets are ever included."""

    service: str
    environment: str
    # Seam for D5: the deterministic orchestration state machine lives in this service.
    orchestration: str
    # Placeholder pipeline stages from docs/design.md §3 — informational only in v1.
    pipeline_stages: list[str]
    # Readiness flags (booleans only — never the underlying credentials/connection strings).
    llm_configured: bool
    # Optional error string when llm_configured is false, so status is honest about
    # why the configured backend could not construct a live provider object.
    llm_error: str | None = None
    # True once MONGO_URL is set — the work-state layer (D3) has a datastore to talk to.
    mongo_configured: bool


# --- Dashboard read-model (the shared work queue, Item 3) --------------------------------------
#
# The BFF renders the dashboard from these denormalized QueueItems and computes the flat,
# attribution-only "needs my action" predicate over them (the predicate lives in web/ where it is
# unit-tested). Fields are snake_case to match the existing wire contracts (StatusResponse), so the
# TS interface mirrors them 1:1 with no mapping layer. NOTHING here is a permission gate — every
# attribution field (owner / assigned_experts / creator / triggered_by) is informational (§1.17).


class FailedJobRef(BaseModel):
    """A failed/stuck batch job attached to a piece (Item 4: failures flag, never roll back)."""

    type: str  # oracle | draft | council | incorporate | finalize
    code: str
    message: str
    triggered_by: str | None = None  # attribution — powers the "you triggered this" predicate branch
    retryable: bool = False
    cost: float = 0.0


class OpenInterviewRef(BaseModel):
    """An open interview session on a piece, with the expert it is assigned to (attribution)."""

    interview_id: str
    expert: str | None = None


class QueueItem(BaseModel):
    """One card in the shared queue: either a Piece across its lifecycle or a Spike from the pool.

    Denormalized so the BFF needs no further joins: the council aggregate, open GAP/clearance
    counts, failed job, proposed-lesson count, open interviews, and latest review round are all
    resolved here.
    """

    kind: Literal["piece", "spike"]
    id: str
    title: str
    voice: str | None = None

    # Pieces carry a stage (one of the 9 states); spikes carry a pool status.
    stage: str | None = None
    spike_status: str | None = None

    # Attribution (never a gate).
    owner: str | None = None
    assigned_experts: list[str] = Field(default_factory=list)
    creator: str | None = None  # spike creator / coordinator attribution

    council_aggregate: float | None = None
    open_gaps: int = 0
    open_clearances: int = 0
    review_round: int | None = None

    # Predicate signals.
    open_interviews: list[OpenInterviewRef] = Field(default_factory=list)
    has_complete_interview: bool = False
    failed_job: FailedJobRef | None = None
    lessons_proposed: int = 0
    spike_assigned: bool = False  # a picked spike that already has an assigned expert / piece

    # Staleness triage (cmw-staleness-timestamps): `updated_at` is the last write of ANY kind
    # (including a batch job completing, with no human involved); `last_human_touch_at` is the
    # narrower "a person actually acted on this" signal (see `app.orchestration.machine`/
    # `app.interview.engine` for exactly what counts). Spikes have no human-touch tracking (the
    # concept only exists for pieces so far) — always `None` for a spike card.
    updated_at: datetime | None = None
    last_human_touch_at: datetime | None = None

    # Provenance (cmw-brain-pieces-visibility): True when this card's Piece was registered from
    # a brain-authored drafts/ folder by the brain-draft sync (app.brain_sync) rather than
    # created through the pipeline. Always False for spike cards.
    brain_synced: bool = False


class DashboardResponse(BaseModel):
    """The whole shared queue plus provenance so the UI can label seeded placeholder data."""

    # "store" = read from the real Mongo work-state; "seed" = built-in placeholder entities used
    # until upstream orchestration writes real work-state (the walking-skeleton path).
    source: Literal["store", "seed"]
    items: list[QueueItem]


class IngestRequest(BaseModel):
    """Push/on-refresh ingest payload (D9). Connector-agnostic: raw content + origin + metadata.

    The lake computes the hybrid index on ingest; connectors never supply embeddings/tokens.
    """

    raw_content: str
    source_id: str  # origin Source registry id (§1.3)
    classification: str  # "scraped-periodically" | "read-as-needed", inherited from the Source
    # Structured metadata (date/recency, author, tags, title, url, extra); shape = ContentMetadata.
    metadata: dict[str, Any] = Field(default_factory=dict)


class IngestResponse(BaseModel):
    id: str
    indexed: bool


# --- Connectors (D8): on-demand refresh + credential-free clip-in -----------------------------


class RefreshRequest(BaseModel):
    """Trigger an on-demand refresh of Green-connector sources (D7 — no scheduler).

    All fields optional: empty refreshes every enabled scraped-periodically source. ``source_id``
    targets one source; ``kinds`` narrows to connector kinds; ``lookback_days`` overrides the
    per-source default window.
    """

    source_id: str | None = None
    kinds: list[str] = Field(default_factory=list)
    lookback_days: int | None = None


class RefreshResultOut(BaseModel):
    """Per-source refresh outcome. ``error`` is set (and counts are 0) when a source failed —
    one failing source never blocks the others (warns, does not block)."""

    source_id: str
    kind: str
    ingested: int = 0
    skipped: int = 0
    error: str | None = None


class RefreshResponse(BaseModel):
    refreshed: list[RefreshResultOut]


class ClipInRequest(BaseModel):
    """Credential-free LinkedIn/X clip-in (D8): pasted material + minimal human-supplied metadata.

    No fetch, no scraper, nothing to authenticate. ``source_id`` must reference a linkedin-x-clip
    source; the item lands in the lake as ``read-as-needed``.
    """

    source_id: str
    content: str  # the pasted text (or a note about a pasted URL)
    url: str | None = None
    author: str | None = None  # source person/account
    content_date: datetime | None = None
    tags: list[str] = Field(default_factory=list)
    title: str | None = None


class ClipInResponse(BaseModel):
    id: str
    classification: str
    indexed: bool


# --- Lessons loop (domain model §1.18; D12) ----------------------------------------------------


class LessonOut(BaseModel):
    """One Lesson (proposed, accepted, or rejected) — the wire shape for both the propose result
    and the read endpoints the voice-kit UI (a separate ticket) will list from."""

    id: str
    voice: str
    source_piece_id: str | None = None
    observed_change: str
    generalizable_rule: str
    status: str


class ProposeLessonsRequest(BaseModel):
    """The input the D12 loop needs that nothing else in the service already holds: the author's
    actually-published/edited text, diffed against the machine's final Git revision."""

    published_content: str
    actor: str | None = None


class ProposeLessonsResponse(BaseModel):
    proposed: list[LessonOut]


class LessonDecisionRequest(BaseModel):
    """Body for accept/reject. ``rule_text`` is accept-only: an edited phrasing that overrides the
    proposed rule — "accept/edit/reject in one click" (D12) folds edit into accept."""

    rule_text: str | None = None
    actor: str | None = None


class LessonPreviewOut(BaseModel):
    """Git diff of the rule about to land in ``content-lessons.md`` (does not write)."""

    lesson_id: str
    path: str
    before: str
    after: str
    rule_text: str


class LessonBatchRequest(BaseModel):
    """Accept or reject several pending lessons in one call (voice-kit batch review)."""

    action: Literal["accept", "reject"]
    lesson_ids: list[str] = Field(min_length=1)
    rule_texts: dict[str, str] | None = None
    actor: str | None = None


class LessonBatchError(BaseModel):
    id: str
    error: str


class LessonBatchResponse(BaseModel):
    decided: list[LessonOut]
    errors: list[LessonBatchError] = Field(default_factory=list)


class DerivativeQualityOut(BaseModel):
    """The derivative quality bar projected for operator surfaces (app.derivatives.quality).

    Every publishable native derivative clears ITS OWN council at ``bar`` with a destination-
    specific editor lineup, while ``universal_gates`` apply to every destination. A child
    artifact that was never promoted has no council of its own, so it reports ``cleared:
    false`` with the honest reason rather than a fake pass.
    """

    required: bool = True
    cleared: bool
    bar: float
    aggregate: float | None = None
    council_revision: str | None = None
    reasons: list[str] = Field(default_factory=list)
    editors: list[str] = Field(default_factory=list)
    universal_gates: list[str] = Field(default_factory=list)


class DerivativeArtifactOut(BaseModel):
    """A native-format follow-on of an anchor piece (child by default; promoted to a Piece)."""

    id: str
    anchor_piece_id: str
    content_project_id: str | None = None
    destination: str
    title: str
    voice: str | None = None
    lineage: str
    promoted_piece_id: str | None = None
    quality: DerivativeQualityOut | None = None


class CreateDerivativeRequest(BaseModel):
    destination: str = Field(min_length=1)
    title: str | None = None


class PromoteDerivativeRequest(BaseModel):
    owner: str | None = None
    actor: str | None = None


# --- Source registry (Item 6 / D8): manage what the Oracle reads ------------------------------


class SourceOut(BaseModel):
    """Wire shape for one Source registry entry. Never carries credentials (D14) — the ``Source``
    model itself rejects credential-looking config keys, so this is a safe 1:1 projection."""

    id: str
    display_name: str
    kind: str
    classification: str
    enabled: bool
    lookback_default_days: int
    config: dict[str, Any] = Field(default_factory=dict)
    owner: str | None = None
    last_refreshed: datetime | None = None


class SourceListResponse(BaseModel):
    # "store" = real Mongo work-state; "seed" = built-in placeholder rows (walking-skeleton path,
    # mirrors the dashboard's source/seed convention) until an admin adds real sources.
    source: Literal["store", "seed"]
    items: list[SourceOut]


class SourceCreateRequest(BaseModel):
    """Add a source (Green connector or the LinkedIn/X clip-in source). Sets WHAT to read, never
    secrets — credentials are provisioned server-side by an admin (D14)."""

    display_name: str
    kind: str
    classification: str
    lookback_default_days: int = 7
    config: dict[str, Any] = Field(default_factory=dict)
    owner: str | None = None


class SourceUpdateRequest(BaseModel):
    """Partial edit of a source: display name, classification, enabled toggle, lookback window,
    or config. ``kind`` is immutable after creation — retire and add a new source to change it."""

    display_name: str | None = None
    classification: str | None = None
    enabled: bool | None = None
    lookback_default_days: int | None = None
    config: dict[str, Any] | None = None
    owner: str | None = None


class SourceDeleteResponse(BaseModel):
    id: str
    deleted: bool


# --- Piece detail read-model (screen 2, cmw-ui-wireframes) --------------------------------------
#
# One piece across its whole lifecycle: work-state joined with the Git-content draft (the semantic
# draft.html, editorial block INCLUDED — this view is where GAPs/clearances are meant to be seen,
# unlike external share/finalize which strip it), the structured Council record, the latest
# ReviewRound, open Interviews, proposed Lessons, and a synthesized activity/routing log.


class EditorScoreOut(BaseModel):
    editor: str
    score: float
    mandatory: bool  # slop-allergist / voice-guardian — never skipped (§1.13)
    editorial_fixes: list[str] = Field(default_factory=list)
    information_gaps: list[str] = Field(default_factory=list)
    clearances: list[str] = Field(default_factory=list)
    hard_cap_applied: bool = False


class CouncilOut(BaseModel):
    round_number: int
    iteration: int = 1
    revision: str
    aggregate: float | None = None
    cost: float = 0.0
    stop_reason: str | None = None
    stop_message: str | None = None
    editor_scores: list[EditorScoreOut] = Field(default_factory=list)


class ReviewRoundOut(BaseModel):
    round_number: int
    minted_from_revision: str
    status: str
    share_mode: str
    doc_url: str | None = None
    opened_at: datetime | None = None
    # The auditable "which items were applied, which routed, which vaulted" trail
    # (`app.review.routing.route_non_fix_items`) — one line per non-editorial-fix feedback item.
    # Empty until `IncorporateStep` actually closes this round.
    routing_log: list[str] = Field(default_factory=list)


class DocRefOut(BaseModel):
    """The final Google Doc of record (D13/use case G; domain model §1.19) — link/metadata only,
    the same shape as a review round's transient ``DocRef`` but recorded permanently on the Piece."""

    doc_id: str | None = None
    url: str | None = None
    share_mode: str = "internal"


class DriveFileRefOut(BaseModel):
    """An ordinary Drive file (branded HTML/PDF, cmw-drive-piece-folders) — link/metadata only, no
    ``share_mode`` (unlike ``DocRefOut``): visibility comes from Shared Drive membership or the
    folder, not a per-file share grant."""

    file_id: str | None = None
    url: str | None = None


class InterviewOut(BaseModel):
    interview_id: str
    assigned_expert: str | None = None
    status: str
    about: str | None = None
    is_gap_interview: bool = False


class ActivityEntry(BaseModel):
    """One synthesized line in the activity/routing log — derived from real joined records
    (jobs/council/review-round/interview timestamps), not a separate stored entity."""

    label: str
    detail: str | None = None
    at: datetime | None = None


class EvidenceSourceOut(BaseModel):
    """One entry in a piece's retrieval/source list — parsed read-time from the piece's own Git
    content (``app.evidence``), never a separate store. ``kind="footnote"`` entries are the
    draft's ``<li id="srcN">`` sources the in-text citation chips point at (``chip`` carries the
    visible marker, e.g. "2"); ``kind="sources-md"`` entries are the research citations in
    ``sources.md``, grouped under the file's own headings (``section``)."""

    id: str
    kind: str  # "footnote" | "sources-md"
    chip: str | None = None
    label: str
    urls: list[str] = Field(default_factory=list)
    section: str | None = None


class EvidenceCitationOut(BaseModel):
    """One claim-level citation chip in the draft body: the visible marker (``chip``), the
    source entry it references (``source_id`` — an ``EvidenceSourceOut.id``), and the chip's own
    in-draft anchor (``anchor_id``, e.g. ``r1``) so a UI can round-trip back-link clicks."""

    chip: str
    source_id: str
    anchor_id: str | None = None


class PersonaListResponse(BaseModel):
    """The Git brain's persona roster for one kind (§1.2) — populates the kickoff interviewer
    picker (screen 6) without hardcoding a list that would drift from the brain. The voice-slug
    counterpart (``VoiceListResponse``) lives further below, alongside the rest of the voice-kit
    schemas (``agents/app/voices.py``'s full view/edit/rollback CRUD already serves it)."""

    kind: str
    personas: list[str]


# --- Spikes & Vault (domain model §1.6/§1.7; D15) -----------------------------------------------
#
# The Spikes & Vault browser (screen 5) reads the full pool via GET /api/spikes; the D15 filters
# (creator/topic/date/status) and convergence sort are applied client-side in web/, mirroring the
# dashboard's FilterBar discipline (lib/dashboard/filters.ts) rather than duplicating query params
# here. POST /api/spikes/{id}/pick is the use-case-C hand-off: pick a spike -> create its Piece.


class SpikeOriginOut(BaseModel):
    kind: str  # oracle-run | narrative | tangent | feedback
    ref: str | None = None


class DistributionIntentOut(BaseModel):
    audience: str | None = None
    angle: str | None = None


class SpikeOut(BaseModel):
    id: str
    headline: str
    status: str  # proposed | picked | in-flight | vaulted
    convergence_score: float | None = None
    creator: str  # attribution — never a lock (D15)
    origin: SpikeOriginOut
    source_ids: list[str] = Field(default_factory=list)
    customer_partner: str | None = None
    outcome_metric: str | None = None
    rank_rationale: str | None = None
    convergence_note: str | None = None
    intent: DistributionIntentOut | None = None
    piece_id: str | None = None  # set once picked
    updated_at: datetime | None = None


class SpikeListResponse(BaseModel):
    # "store" = real Mongo work-state; "seed" = the same placeholder spikes the dashboard's
    # "Spikes & Vault" tab already shows (app.dashboard.seed_work_state), so the two surfaces never
    # diverge before upstream orchestration writes anything real.
    source: Literal["store", "seed"]
    items: list[SpikeOut]


class PickSpikeRequest(BaseModel):
    """Kickoff steps 1-2 (screen 6): pick the spike, create its Piece, AND open its first
    Interview — all in one all-or-nothing call (cmw-piece-interviewing-without-interview). A piece
    must never sit in `interviewing` with no Interview to conduct: that used to be two separate
    steps (create the piece, then a later "generate link" click), and a piece that never got its
    link generated was indistinguishable from a genuinely broken one. The spike's own
    `creator`/`origin` attribution is untouched — ownership is attribution, not a lock (D15)."""

    voice: str
    slug: str | None = None  # defaults to a slugified headline
    title: str | None = None  # defaults to the spike's headline
    target: str | None = None  # blog / FAQ / LinkedIn… (carried target/audience intent)
    owner: str | None = None  # the picker/coordinator — attribution only
    # Required (validated non-empty + real persona names in the handler, not here, so the
    # 404/409 spike-lookup checks still run first against a malformed request) — see
    # `app.interview.engine.InterviewEngine.open_interview`.
    interviewer_personas: list[str] = Field(default_factory=list)
    assigned_expert: str | None = None
    about: str | None = None  # defaults to the spike's headline


class PickSpikeResponse(BaseModel):
    piece_id: str
    slug: str
    spike: SpikeOut  # the now-`picked` spike, for the caller to refresh its view
    interview_id: str  # the Interview opened atomically with the piece


class MintSpikeFromNarrativeRequest(BaseModel):
    """The "new piece from my own idea" fast path (Option B, cmw-narrative-first-entry-point):
    mint a Spike straight from an existing Narrative with no Oracle ranking run, skipping the
    ranked-spikes review table entirely. Still produces a real, persisted, `origin.kind=narrative`
    Spike — the input `DraftStep._purpose_block` needs to hydrate a piece's purpose; a spike-less
    piece silently reintroduces the wrong-subject-draft bug PR #74 fixed (see that module's
    docstring). `convergence_score`/`rank_rationale`/`convergence_note` are correctly left null on
    the resulting spike — nothing ranked this idea against source material."""

    narrative_id: str
    headline: str  # a short working title — becomes the spike headline and default piece title
    creator: str | None = None  # defaults to the narrative's own author


# --- Narrative (domain model §1.5) — Oracle Entry B's seed --------------------------------------


class NarrativeCreateRequest(BaseModel):
    author: str | None = None
    seed_text: str
    audience: str | None = None
    angle: str | None = None


class NarrativeOut(BaseModel):
    id: str
    author: str
    seed_text: str
    intent: DistributionIntentOut
    oracle_run_id: str | None = None  # set once the Oracle run it seeded completes


class PieceDetailResponse(BaseModel):
    id: str
    slug: str
    title: str
    voice: str
    stage: str  # one of the settled 9 states (domain model §1.9)
    owner: str | None = None
    assigned_experts: list[str] = Field(default_factory=list)
    origin_spike_id: str | None = None
    target: str | None = None
    partners: list[str] = Field(default_factory=list)

    open_gaps: int = 0
    open_clearances: int = 0
    latest_revision: str | None = None

    # Staleness triage (cmw-staleness-timestamps) — same two-timestamp distinction as
    # `QueueItem` above: `updated_at` is "when did anything last write this piece" (any write
    # path, including a machine-only batch job); `last_human_touch_at` is "when did a person last
    # act on it" (a `PieceMachine` human trigger, or answering/editing an interview turn — never a
    # batch job completing on its own). `None` for either means it hasn't happened yet.
    created_at: datetime | None = None
    updated_at: datetime | None = None
    last_human_touch_at: datetime | None = None

    # The semantic draft.html master, editorial block included. `None` when the piece has no
    # committed revision yet (e.g. still `interviewing`) or the Git brain is unreachable. For a
    # brain-authored direct-authored piece (no draft.html; content in piece.md) this carries the
    # piece.md content section rendered to HTML instead (app.piece_md) — readable either way.
    draft_html: str | None = None

    # True when the Mongo record was minted by the brain-draft sync (app.brain_sync) for a
    # brain-authored draft folder — provenance only; pipeline-created pieces are always false.
    brain_synced: bool = False

    # True when this response was assembled from the built-in seed work-state (same
    # store-or-seed fallback as `/api/dashboard`'s `source` field — no real Mongo document backs
    # this piece). Provenance for the piece-detail screen's "seeded data" badge: clicking through
    # from a seeded list must not lose the placeholder context (cmw-boss-facing-presentation).
    seeded: bool = False

    council: CouncilOut | None = None
    review_round: ReviewRoundOut | None = None
    # EVERY round the piece has had (ascending), each carrying its own `routing_log` — the
    # between-rounds routing log (piece-detail's own always-visible card, not gated to the review
    # screen): "what happened between rounds and where content went." `review_round` above stays
    # the single latest-round convenience field existing callers (ReviewDocLink) already use.
    review_rounds: list[ReviewRoundOut] = Field(default_factory=list)
    interviews: list[InterviewOut] = Field(default_factory=list)
    failures: list[FailedJobRef] = Field(default_factory=list)
    lessons: list[LessonOut] = Field(default_factory=list)
    activity: list[ActivityEntry] = Field(default_factory=list)

    # The piece's evidence trail (claim-level citation chips + the full retrieval/source list;
    # parsed read-time from draft.html + sources.md by app.evidence — never a separate store).
    # Both empty when the piece carries no evidence annotations yet.
    evidence_sources: list[EvidenceSourceOut] = Field(default_factory=list)
    evidence_citations: list[EvidenceCitationOut] = Field(default_factory=list)

    # Finalize outputs (D13, use case G/J; domain model §1.19): the final Doc link + render
    # provenance, so the finalize/outputs screen can show "source revision + template version"
    # and the Doc of record. `None` until the piece has been finalized at least once. The branded
    # HTML/PDF themselves are disposable renders and are not recorded here (§1.19).
    final_doc: DocRefOut | None = None
    final_template_version: str | None = None
    final_rendered_at: datetime | None = None

    # Per-piece Google Drive folder (cmw-drive-named-folder-scoping) — `None` until
    # GOOGLE_DRIVE_ROOT_FOLDER_NAME is configured and this piece has produced its first Google
    # artifact.
    # A convenience "open everything for this piece" link (app/drive/folder.py): sharing this one
    # folder, or simply having access to the named My-Drive root under it, gives a reviewer every
    # Google artifact the piece has produced. `final_drive_html`/`final_drive_pdf` are the
    # Drive-side copies of the
    # same branded render `final_doc`/`OutputsList` already track — real, unconverted files, not
    # disposable the way the render itself is (§1.19); only their Drive location is recorded.
    drive_folder_url: str | None = None
    final_drive_html: DriveFileRefOut | None = None
    final_drive_pdf: DriveFileRefOut | None = None

    # Published outputs (finalized → published HITL button; §1.19-exception, see
    # docs/design.md's D13 note and models/piece.py). Unlike `final_doc` above, these ARE durable
    # and public by design: `published_release` is `0` until the piece has ever been published,
    # then increments on every subsequent publish (each mints a fresh, immutable S3/Doc snapshot
    # rather than overwriting the prior one — see agents/app/publish/README.md).
    published_release: int = 0
    published_html_url: str | None = None
    published_pdf_url: str | None = None
    published_doc: DocRefOut | None = None
    published_at: datetime | None = None
    # The same release's Drive-side copies, in the piece folder's `Published/` subfolder
    # (cmw-drive-piece-folders) — `None` whenever no Shared Drive folder was available at publish
    # time, exactly like `published_html_url`/`published_pdf_url` are `None` before any publish.
    published_drive_html: DriveFileRefOut | None = None
    published_drive_pdf: DriveFileRefOut | None = None

    # Archive (triage at scale) — orthogonal to `stage`, never a `PieceStage` value. `None` means
    # never archived. Still fully served here regardless: only the dashboard queue excludes an
    # archived piece (`app.dashboard.build_queue`) — direct-by-id access is unaffected.
    archived_at: datetime | None = None

    # Lineage (cmw-lesson-lineage-impl): set when this Piece was promoted from a child derivative
    # artifact of another piece. `None` for anchors and pre-lineage pieces. Optional so existing
    # fixtures don't need updating.
    parent_piece_id: str | None = None
    role: str | None = None


class PieceArchiveResponse(BaseModel):
    """The wire shape for ``POST /api/pieces/{id}/{archive,unarchive}`` (`app.pieces`)."""

    id: str
    slug: str
    archived_at: datetime | None = None


class RecentPiece(BaseModel):
    """One row of the recent-pieces projection (``GET /api/pieces/recent``, `app.pieces`).

    Deliberately narrower than :class:`QueueItem`: the desk's recent-pieces card needs identity +
    stage + recency, not the dashboard's full join (council aggregate, failed jobs, lessons…).
    `updated_at` is the sort key ("most recently created/active" — every write bumps it, see the
    cmw-staleness-timestamps notes); `last_human_touch_at` rides along so a UI can prefer the
    human signal when it has one, same pairing as `QueueItem`.
    """

    id: str
    title: str | None = None
    slug: str
    stage: str
    voice: str | None = None
    owner: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    last_human_touch_at: datetime | None = None


class RecentPiecesResponse(BaseModel):
    """The recent-pieces projection plus provenance.

    `source` is `"store"` when read from the real Mongo work-state and `"none"` when Mongo is not
    configured. There is deliberately NO seed fallback here (unlike `/api/dashboard`): the desk's
    recent-pieces card exists to show REAL pieces — a hardcoded placeholder list is exactly the
    thing it replaces, so an unconfigured/empty deploy reports an honest empty list instead.
    """

    source: Literal["store", "none"]
    items: list[RecentPiece]


# --- Voice kit (screen 11 / D12; domain model §1.1): view/edit/rollback Git-backed voice packs ---
#
# The wire shape for `app/voices.py`. `VoiceFileKey` is the fixed set of pack files a voice-kit
# screen can address — the same keys `app.git.brain.VoicePack` uses, kept independent so the Git
# module stays framework-free (mirrors the LessonOut/Lesson split).

VoiceFileKey = Literal[
    "voice_guide", "style_guide", "content_lessons", "visual_identity", "brand_guidelines"
]


class VoiceListResponse(BaseModel):
    voices: list[str]


class VoicePackOut(BaseModel):
    slug: str
    voice_guide: str | None = None
    style_guide: str | None = None
    content_lessons: str | None = None
    visual_identity: str | None = None
    brand_guidelines: str | None = None


class VoiceCommitOut(BaseModel):
    sha: str
    author_name: str
    author_email: str
    date: str
    message: str


class VoiceFileHistoryResponse(BaseModel):
    commits: list[VoiceCommitOut]


class VoiceFileContentResponse(BaseModel):
    content: str


class VoiceFileUpdateRequest(BaseModel):
    content: str
    message: str
    actor: str | None = None
    actor_name: str | None = None


class VoiceFileRollbackRequest(BaseModel):
    sha: str
    message: str | None = None
    actor: str | None = None
    actor_name: str | None = None


# --- Brain drafts view (cmw-drafts-view) -------------------------------------------------------
#
# Read-only reading surface for brain-authored ``drafts/<slug>/`` content — live from Git,
# additive to the existing Google-Doc review/finalize flow.


class BrainDraftItem(BaseModel):
    """One row in the brain drafts list."""

    slug: str
    title: str
    voice: str | None = None
    target: str | None = None
    partners: list[str] = Field(default_factory=list)
    has_html: bool = False
    has_piece_md: bool = False
    revision: str | None = None
    updated_at: str | None = None


class PieceTitleUpdateRequest(BaseModel):
    title: str | None = None


class PieceTitleUpdateResponse(BaseModel):
    id: str
    slug: str
    title: str | None = None
    updated_at: datetime | None = None


class BrainDraftListResponse(BaseModel):
    items: list[BrainDraftItem]


class BrainDraftDetailResponse(BaseModel):
    """A single draft rendered for reading, with additive Google-Doc links when available."""

    slug: str
    title: str
    voice: str | None = None
    target: str | None = None
    partners: list[str] = Field(default_factory=list)
    content_kind: str  # "html" | "markdown"
    draft_html: str | None = None
    revision: str | None = None
    updated_at: str | None = None
    review_doc_url: str | None = None
    final_doc_url: str | None = None
