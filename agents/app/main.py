"""FastAPI application entrypoint.

v1 walking skeleton: exposes /health and one /api/status stub the Next.js BFF calls over
REST. The deterministic orchestration state machine (D5) and the LLM module (D14) are still
downstream tickets. The MongoDB **work-state** data layer (D3) is wired here via a lifespan
seam: on startup, if MONGO_URL is configured, a WorkStateStore is attached to app.state for
downstream route handlers/orchestration to use. The content-lake hybrid index (D9) remains a
separate ticket.
"""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from dataclasses import replace

from fastapi import FastAPI, HTTPException, Request

from app import __version__
from app.brain_sync import router as brain_sync_router, sync_brain_pieces
from app.config import get_settings
from app.connectors.refresh import build_connectors
from app.connectors.routes import router as connectors_router
from app.dashboard import build_queue, load_collections, seed_work_state
from app.db import create_client, get_database
from app.drafts import router as drafts_router
from app.git import (
    BrainAvailability,
    GitContentStore,
    GitError,
    ensure_brain_available,
    open_brain,
    open_content_store,
    refresh_brain,
)
from app.interview import InterviewEngine
from app.interview.routes import router as interview_router
from app.lake import build_content_lake
from app.lake.routes import router as lake_router
from app.lessons.routes import router as lessons_router
from app.narratives import router as narratives_router
from app.oracle import OracleStep
from app.oracle.routes import router as oracle_router
from app.orchestration import JobRunner, PieceMachine, StepRegistry
from app.orchestration.council_step import CouncilStep
from app.orchestration.draft_step import DraftStep
from app.orchestration.routes import router as orchestration_router
from app.personas import router as personas_router
from app.piece_detail import build_piece_detail, draft_content_from_files, find_piece_collections, read_draft_content
from app.derivatives.routes import router as derivatives_router
from app.pieces import router as pieces_router
from app.publish.routes import router as publish_router
from app.render import build_finalize_step
from app.repositories import WorkStateStore
from app.review import HttpReviewDocsClient, IncorporateStep
from app.review.routes import router as review_router
from app.schemas import (
    BrainPullResponse,
    BrainStatusResponse,
    DashboardResponse,
    HealthResponse,
    PieceDetailResponse,
    StatusResponse,
)
from app.sources import router as sources_router
from app.spikes import router as spikes_router
from app.voices import router as voices_router
from app.content_workflow.routes import router as content_workflow_router

logger = logging.getLogger(__name__)

# Pipeline stages from docs/design.md §3 — informational placeholder for the state machine.
PIPELINE_STAGES = [
    "oracle",
    "interview",
    "draft",
    "council",
    "review",
    "revision",
    "finalize",
    "lessons",
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Connect the Mongo work-state layer on startup (seam for D3), if configured.

    No-op when MONGO_URL is unset, so the service still boots for pure-skeleton use and tests.
    The connection string is read server-side only and never exposed to clients (D14).
    """
    settings = get_settings()
    client = None
    # Git brain/content (D1/D2/D4) needs no Mongo — just the on-disk brain clone (BRAIN_ROOT,
    # cloned/refreshed from BRAIN_REPO_URL by ensure_brain_available when configured). Degrades to
    # None (rather than failing app boot) when brain_root isn't a git repo, mirroring the
    # Mongo-unconfigured philosophy below; the lessons/lake/orchestration seams that need it report
    # 503 instead. Never fatal: a POC that refuses to boot over an optional subsystem being down
    # would be a worse failure mode than degrading — but degrading must not mean *silent*, so the
    # real failure (if any) is logged here and carried on `app.state.brain_availability` for
    # `/api/brain/status` to report (see BrainAvailability).
    brain_availability = ensure_brain_available(settings)
    try:
        app.state.git_brain = open_brain()
        app.state.git_content = open_content_store()
    except GitError as exc:
        logger.warning("brain clone at %s is not usable: %s", settings.brain_root, exc)
        app.state.git_brain = None
        app.state.git_content = None
        # Only promote this to a reported `error` when a brain was actually configured
        # (BRAIN_REPO_URL set, so an auto-managed clone/pull was expected this boot) — when it
        # wasn't, an unusable BRAIN_ROOT is the normal, by-design local-dev shape (a developer who
        # hasn't cloned their own brain yet), not a failure worth alarming on. And only fill in the
        # reason if ensure_brain_available's own clone/pull attempt didn't already fail for a
        # (usually root-cause) reason — that message is more specific than "not a git repo," which
        # is often just the downstream symptom of the same failure.
        if brain_availability.configured and brain_availability.error is None:
            brain_availability = replace(brain_availability, error=str(exc))
    app.state.brain_availability = brain_availability
    if settings.has_mongo():
        client = create_client(settings)
        database = get_database(client, settings)
        app.state.mongo_client = client
        store = WorkStateStore(database)
        app.state.work_state = store
        # Same Mongo instance backs the content lake (§7); attach it for the ingest/query API (D9).
        app.state.content_lake = build_content_lake(database, settings)
        # Green connectors (D8), wired with their server-side clients from Settings (D14). The
        # refresh routes read the registry + lake off app.state; this pre-builds the connectors.
        app.state.connectors = build_connectors(settings)
        # Orchestration core (D5): the deterministic state machine + job runner, hosted here.
        # The batch-step registry now carries every real step (oracle/draft/council/incorporate/
        # finalize); the LLM provider is wired in when a key is configured. A per-run cost ceiling
        # (the one hard block, D14) is set from settings.
        # Provider selection can fail (a misconfigured/missing credential for whichever backend
        # is actually selected) — guarded the same way build_finalize_step(settings) below degrades
        # an optional subsystem: log and leave provider=None rather than crashing boot. Without
        # this guard, e.g. LLM_BACKEND=openai with no ANTHROPIC_API_KEY fell through to the
        # Anthropic elif branch (has_llm_credentials() checks anthropic/openai keys, not which backend
        # is selected) and raised RuntimeError straight out of the lifespan.
        provider = None
        try:
            if settings.llm_backend == "bedrock":
                from app.llm import BedrockGLMProvider

                provider = BedrockGLMProvider.from_settings(settings)
            elif settings.llm_backend in ("openai", "openrouter"):
                from app.llm import OpenAILLMProvider

                # Both backends speak the OpenAI-compatible API; "openrouter" is just that
                # path pointed at OpenRouter. OPENAI_BASE_URL (settings.openai_base_url) is the
                # explicit override for both; the "openrouter" fallback default is the
                # OpenRouter endpoint, "openai" keeps the SDK default (api.openai.com — or the
                # OPENAI_BASE_URL env var the SDK itself reads, the pre-existing implicit
                # OpenRouter path, so LLM_BACKEND=openai behavior is unchanged).
                base_url = settings.openai_base_url or None
                if settings.llm_backend == "openrouter" and base_url is None:
                    base_url = "https://openrouter.ai/api/v1"
                provider = OpenAILLMProvider(
                    api_key=settings.openai_api_key,
                    base_url=base_url,
                    default_effort=settings.openai_reasoning_effort or None,
                )
            elif settings.has_llm_credentials():
                from app.llm import AnthropicLLMProvider

                provider = AnthropicLLMProvider.from_settings(settings)
        except Exception as exc:
            # Broad catch: BedrockGLMProvider.from_settings raises
            # botocore.exceptions.NoRegionError (not a RuntimeError) when no AWS
            # region is configured — the default local-compose shape. Every other
            # provider path raises RuntimeError (missing API key). A bare exception
            # must degrade gracefully, never crash boot over an optional subsystem.
            logger.warning(
                "LLM provider unavailable for llm_backend=%s: %s", settings.llm_backend, exc
            )
            provider = None
        app.state.llm_provider = provider
        # Initialized to None up front so CouncilStep's register call below can read
        # ``app.state.content_workflow`` guarded before the Mongo-configured branch (further down)
        # assigns the real ContentWorkflow. Regression for the #156-induced boot crash: reading the
        # attribute before it existed took the whole service down (2026-08-31 live P0).
        app.state.content_workflow = None
        registry = StepRegistry()
        registry.register(OracleStep())
        registry.register(DraftStep())
        registry.register(
            CouncilStep(
                settings=settings,
                workflow_state=app.state.content_workflow.state if app.state.content_workflow else None,
            )
        )
        # FinalizeStep's construction (unlike the other steps here) touches the brain clone eagerly
        # — TemplateStore's constructor calls discover_repo on brain_root immediately, rather than
        # degrading lazily at call time like the other steps' `ctx.brain is None` checks. Guard it
        # the same way the git_brain/git_content pair above degrades: log and leave finalize
        # unregistered rather than crashing boot. `registry.has(JobType.finalize)` then reports
        # False exactly like any other not-yet-implemented step, so the finalize trigger cleanly
        # 501s (app/orchestration/routes.py's StepNotRegistered handling) instead of taking the
        # whole service down over one optional, misconfigured dependency.
        try:
            registry.register(build_finalize_step(settings))
        except GitError as exc:
            logger.warning(
                "finalize step unavailable: brain clone at %s is not usable: %s",
                settings.brain_root,
                exc,
            )
        # Registered unconditionally, like Oracle above — never gated on
        # GOOGLE_OAUTH_CLIENT_ID/_SECRET/_REFRESH_TOKEN at boot. HttpReviewDocsClient defers all
        # credential validation to call time (`_require_creds()`, app/render/docs_export.py), the
        # same lazy-degrade idiom IncorporateStep already applies to `ctx.provider is None` above —
        # so an unconfigured deploy fails cleanly *inside* a dispatched job (a "no open review
        # round"/"Google Docs export not configured" PermanentStepError surfaced through the
        # piece's `failures`), never as a permanent 501 on this endpoint. Gating registration
        # itself on credential presence was considered (see app/review/README.md's prior
        # integration note) but rejected: it would leave `reviews-done` 501ing forever in an
        # unconfigured deploy, indistinguishable from "not implemented" even once implemented.
        registry.register(
            IncorporateStep(
                docs_client=HttpReviewDocsClient(
                    settings.google_oauth_client_id,
                    settings.google_oauth_client_secret,
                    settings.google_oauth_refresh_token,
                )
            )
        )
        app.state.step_registry = registry
        # Oracle jobs are pieceless (§1.8) and are dispatched straight through the runner (see
        # app.oracle.routes), not through PieceMachine's piece-stage batch chain — so the runner
        # is exposed on its own alongside the machine (which reuses the same instance). Reuses the
        # ``app.state.git_brain``/``app.state.git_content`` opened above (voices/personas/engine
        # steps, §1.1/§1.2/§7) — either may be ``None`` if brain_root isn't a git repo; most steps
        # degrade via their own ctx checks (falling back to opening their own content store), but
        # FinalizeStep has no such fallback and requires ``ctx.content`` explicitly, so it must be
        # threaded through here.
        runner = JobRunner(
            store,
            registry,
            provider=provider,
            brain=app.state.git_brain,
            content=app.state.git_content,
            lake=app.state.content_lake,
            budget_factory=settings.make_run_budget,
        )
        app.state.job_runner = runner
        # Create a budget factory from settings — the one sanctioned hard block (D14).
        budget_factory = settings.make_run_budget
        app.state.budget_factory = budget_factory
        piece_machine = PieceMachine(store, runner, budget_factory=budget_factory)
        app.state.piece_machine = piece_machine
        # Interview engine (D5-context-assembly §5): reuses the Git brain/content already opened
        # above (no Mongo needed for that half), and drives its four sub-steps through the same
        # LLM provider once one is configured (guarded at call time otherwise).
        app.state.interview_engine = InterviewEngine(
            store,
            app.state.git_content,
            app.state.git_brain,
            provider,
            lake=app.state.content_lake,
            machine=piece_machine,
            budget_factory=budget_factory,
        )
        # ContentWorkflow tracer (§1.5/§1.6): attach using real Mongo store. 503 only when no Mongo.
        from app.content_workflow import ContentWorkflow
        from app.content_workflow.store import MongoWorkflowState

        wf_store = MongoWorkflowState(database)
        app.state.content_workflow = ContentWorkflow(wf_store)
        # Brain-draft visibility auto-discovery (cmw-brain-pieces-visibility): idempotently
        # register brain-authored draft folders (`drafts/<slug>/` the brain wrote on its own,
        # never through this pipeline) as Pieces, so the site's piece lists show them with zero
        # operator steps — a deploy/restart alone makes them visible. Runs ONLY when both Mongo
        # and a usable brain clone are present; never fatal to boot (same degrade-not-crash
        # discipline as every optional subsystem above), never a write to the brain itself.
        if app.state.git_content is not None:
            try:
                await sync_brain_pieces(store, app.state.git_content)
            except Exception as exc:  # noqa: BLE001 — visibility enrichment, never boot-fatal
                logger.warning("brain-draft visibility sync skipped at boot (non-fatal): %s", exc)
    else:
        app.state.mongo_client = None
        app.state.work_state = None
        app.state.content_lake = None
        app.state.connectors = None
        app.state.llm_provider = None
        app.state.llm_provider_error = None
        app.state.step_registry = None
        app.state.job_runner = None
        app.state.budget_factory = None
        app.state.piece_machine = None
        app.state.interview_engine = None
        app.state.content_workflow = None
    try:
        yield
    finally:
        if client is not None:
            client.close()


app = FastAPI(
    title="content-machine agents",
    version=__version__,
    summary="Orchestration + LLM service for the content-machine webapp (v1 skeleton).",
    lifespan=lifespan,
)

# Content-lake ingest/query API (D9). Endpoints 503 until Mongo is configured (see routes).
app.include_router(lake_router)
# Source connectors (D8): on-demand refresh + credential-free clip-in. 503 until Mongo configured.
app.include_router(connectors_router)
# Source registry CRUD (Item 6): list/add/edit/enable-disable/retire. GET falls back to seed rows;
# writes 503 until Mongo is configured.
app.include_router(sources_router)
# Orchestration state-machine API (D5): the human triggers + interactive gates. Endpoints 503
# until Mongo is configured; batch triggers 501 until their step is registered (downstream).
app.include_router(orchestration_router)
# Lessons loop (D12): propose (Opus tier) + accept/reject over REST. 503 until Mongo/Git brain are
# configured; propose additionally 503s until an LLM provider is configured.
app.include_router(lessons_router)
# Oracle (§1.8): the on-demand run entrypoint. 503 until Mongo is configured.
app.include_router(oracle_router)
# Interview engine API (D5-context-assembly §5): the interactive, multi-turn extraction step.
# Endpoints 503 until Mongo is configured.
app.include_router(interview_router)
# Voice kit (screen 11 / D12): view/edit/rollback Git-backed voice packs. Needs only the Git
# brain (independent of Mongo) — 503 only when brain_root isn't a git repo.
app.include_router(voices_router)
# Review round-trip (open-decisions Item 7): mint an internal/external Doc + the assisted "reviews
# done" ingest preview. 503 until Mongo/Git are configured, or until Google Docs credentials are
# set. The actual round-close (collect → classify → apply → route) runs through the existing
# `POST /api/pieces/{id}/reviews-done` trigger, dispatched to the IncorporateStep registered above
# (see app/review/README.md) — no separate route for that half.
app.include_router(review_router)
# Publish (finalized → published HITL button, D13 note): mints durable public S3/Doc outputs then
# closes the terminal transition. 503 until Mongo/Git are configured, or until Google Docs
# credentials / PUBLISHED_ASSETS_BUCKET are set — see app/publish/README.md.
app.include_router(publish_router)
# Brain-draft visibility (cmw-brain-pieces-visibility): POST /api/brain/sync registers
# brain-authored drafts/<slug>/ folders as Pieces so the site's piece lists can see them; the
# piece-list endpoints additionally run the same idempotent sync lazily (see app.brain_sync).
app.include_router(brain_sync_router)
# Brain drafts view (cmw-drafts-view): read-only reading surface for brain-authored
# drafts/<slug>/ content, additive to the Google-Doc review/finalize flow. Needs only Git.
app.include_router(drafts_router)
# Spikes & Vault (§1.6/§1.7, D15): list the pool + pick-a-spike -> create-piece hand-off (use case
# C, screen 6 steps 1-2). GET falls back to the dashboard's seed spikes; writes 503 until Mongo is
# configured.
app.include_router(spikes_router)
# Narrative (§1.5): create the audience/angle-intent seed Oracle Entry B runs against (use case B).
# 503 until Mongo is configured.
app.include_router(narratives_router)
# Read-only Git-brain persona listing (kickoff persona picker, Oracle run panel). Distinct from
# `voices_router` above (which already covers `GET /api/voices` as part of its full CRUD) — this
# module only lists personas. 503 until the brain_root git repo is reachable.
app.include_router(personas_router)
# Archive/unarchive (triage at scale) — deliberately NOT a PieceMachine trigger: a dashboard-
# visibility flag orthogonal to the stage machine, legal regardless of the piece's current stage.
# 503 until Mongo is configured.
app.include_router(pieces_router)
# Derivative lineage (cmw-lesson-lineage-impl): child artifacts of an anchor, promoted to a
# top-level Piece only when they need their own owner/review/publish state. 503 until Mongo.
app.include_router(derivatives_router)
# Thin submit/inspect adapters over ContentWorkflow (vertical tracer only).
app.include_router(content_workflow_router)


@app.get("/health", response_model=HealthResponse, tags=["ops"])
def health() -> HealthResponse:
    """Liveness probe. The Next.js BFF proxies this to prove web/ ↔ agents/ connectivity."""
    return HealthResponse(status="ok", service=get_settings().service_name, version=__version__)


@app.get("/build", tags=["ops"])
def build_info() -> dict:
    """Public, unauthenticated build metadata (commit SHA baked at image build time only).
    Returns only non-sensitive fields; never reads env, config, or other internals.
    """
    try:
        with open("/app/cmw-build.json") as f:
            return json.load(f)
    except Exception:
        return {"component": "agents", "commit": "unknown", "shortCommit": "unknown", "builtAt": None}


@app.get("/api/status", response_model=StatusResponse, tags=["ops"])
def status(request: Request) -> StatusResponse:
    """Stub endpoint the BFF calls. Reports readiness of the downstream seams without ever
    leaking secrets."""
    settings = get_settings()
    provider = getattr(request.app.state, "llm_provider", None)
    llm_error = None
    if provider is None:
        llm_error = getattr(request.app.state, "llm_provider_error", None) or "no live LLM provider"
    # The state machine + job runner are hosted here once Mongo is configured; batch steps that
    # plug into the seam are downstream, so the machine is "hosted" (framework live, steps pending).
    return StatusResponse(
        service=settings.service_name,
        environment=settings.environment,
        orchestration="hosted" if settings.has_mongo() else "stub",
        pipeline_stages=PIPELINE_STAGES,
        llm_configured=provider is not None,
        llm_error=llm_error,
        mongo_configured=settings.has_mongo(),
    )


@app.get("/api/brain/status", response_model=BrainStatusResponse, tags=["ops"])
def brain_status() -> BrainStatusResponse:
    """Provenance for the on-disk brain clone: which commit is checked out and where it was cloned
    from, so the app (and the web/ "brain version" indicator) can answer "which brain am I
    running." No network call here — reports the local clone's state only, cheaply, matching the
    non-blocking readiness-flag philosophy of ``/api/status``.

    ``connected: false`` alone is ambiguous between "no brain configured" and "configured but
    unreachable" — ``configured``/``error`` (from ``app.state.brain_availability``, set in the
    lifespan) disambiguate: ``configured=False`` means no ``BRAIN_REPO_URL`` was ever set (the
    local-dev, self-managed-clone path); ``configured=True`` with a non-null ``error`` means this
    boot's clone/fetch genuinely failed, with the real reason (never a secret — see
    ``ensure_brain_available``)."""
    availability: BrainAvailability | None = getattr(app.state, "brain_availability", None)
    configured = availability.configured if availability else False
    error = availability.error if availability else None
    brain = getattr(app.state, "git_brain", None)
    if brain is None:
        return BrainStatusResponse(connected=False, configured=configured, error=error)
    repo = brain.repo
    history = repo.log(rel_path=brain.prefix or None, max_count=1)
    latest = history[0] if history else None
    return BrainStatusResponse(
        connected=True,
        configured=configured,
        error=error,
        root=str(repo.root),
        remote_url=repo.remote_url(),
        commit_sha=latest.sha if latest else None,
        commit_date=latest.date if latest else None,
        commit_message=latest.message if latest else None,
    )


@app.post("/api/brain/pull", response_model=BrainPullResponse, tags=["ops"])
async def brain_pull() -> BrainPullResponse:
    """Refresh the running clone from its remote on demand — the only way today to pick up a
    hand-nurtured brain edit without recreating the container (clone-on-boot otherwise only
    refreshes once, at startup, via ``ensure_brain_available``).

    Runs ``refresh_brain`` (the exact fast-forward/pin logic boot already runs on an
    already-cloned host) against the SAME already-open ``app.state.git_brain`` repo instance, so
    this behaves identically to what a restart's refresh would have done, minus the downtime.

    **In-flight work:** the underlying pull is a ``git merge --ff-only`` (``GitRepo.pull``) — it
    either fully advances the working tree to the remote tip or aborts cleanly, never leaving a
    conflicted/half-merged state. A request reading a brain file concurrently with the checkout
    can observe either the pre- or post-pull content for that file, the same pre-existing
    read/write race a voice-kit edit already has today — this endpoint adds no new hazard class,
    and a POC's request volume doesn't justify a repo-wide lock ahead of a concrete problem.
    Concurrent git invocations (e.g. this pull racing a voice-kit commit) are already serialized
    by git's own ``.git/*.lock`` files; the loser fails loudly with a ``GitError`` rather than
    corrupting anything.

    **Failure:** never silent (PR #47's precedent for push applies here too) — logged at ``ERROR``,
    raised as a real ``502`` (this is an action trigger, not a passive status read — an ops caller
    checking only the HTTP status, e.g. ``curl -f``, must see it fail) with the real message in
    the response body (never key material), and folded into ``app.state.brain_availability`` so
    ``/api/brain/status`` keeps reflecting it after this call returns too. A repo with no remote
    configured (the self-managed local-dev clone) reports ``pulled=False`` with no error at
    ``200`` instead — a legitimate no-op, not a failure.
    """
    brain = getattr(app.state, "git_brain", None)
    if brain is None:
        raise HTTPException(status_code=503, detail="brain unavailable (brain_root not configured)")
    repo = brain.repo
    if not repo.has_remote():
        return BrainPullResponse(pulled=False)
    settings = get_settings()
    current: BrainAvailability = getattr(app.state, "brain_availability", None) or BrainAvailability(
        configured=False
    )
    try:
        refresh_brain(repo, ref=settings.brain_ref or None)
    except GitError as exc:
        logger.error("on-demand brain pull failed against %s: %s", repo.remote_url(), exc)
        app.state.brain_availability = replace(current, error=str(exc))
        raise HTTPException(status_code=502, detail=f"brain pull failed: {exc}") from exc
    app.state.brain_availability = replace(current, error=None)
    # Brain-draft visibility (cmw-brain-pieces-visibility): a pull may have brought NEW
    # brain-authored draft folders in — re-run the idempotent piece sync so they become visible
    # without waiting for a restart (boot is the other sync point). Best-effort: a sync hiccup
    # must not fail an otherwise-successful pull (the pull itself is the action this endpoint
    # answers); never a write to the brain either way.
    store: WorkStateStore | None = getattr(app.state, "work_state", None)
    content: GitContentStore | None = getattr(app.state, "git_content", None)
    if store is not None and content is not None:
        try:
            await sync_brain_pieces(store, content)
        except Exception as exc:  # noqa: BLE001 — visibility enrichment, never pull-fatal
            logger.warning("post-pull brain-draft sync skipped (non-fatal): %s", exc)
    history = repo.log(rel_path=brain.prefix or None, max_count=1)
    latest = history[0] if history else None
    return BrainPullResponse(
        pulled=True,
        remote_url=repo.remote_url(),
        commit_sha=latest.sha if latest else None,
        commit_date=latest.date if latest else None,
        commit_message=latest.message if latest else None,
    )


@app.get("/api/dashboard", response_model=DashboardResponse, tags=["dashboard"])
async def dashboard(viewer: str | None = None) -> DashboardResponse:
    """The shared work queue (Item 3) the Next.js BFF renders the dashboard from.

    Reads real work-state through the data-layer repositories when Mongo is configured and
    populated; otherwise (and until upstream orchestration writes anything) returns built-in seed
    entities so the walking-skeleton dashboard is populated end-to-end. ``viewer`` is the signed-in
    user's email, forwarded by the BFF: it only attributes the SEED's "needs my action" cards to
    that user — it is never a permission filter (authorization is flat, §1.17), so the full queue is
    always returned and the predicate is computed client-side.
    """
    store: WorkStateStore | None = getattr(app.state, "work_state", None)
    source = "seed"
    collections = None
    if store is not None:
        collections = await load_collections(store)
        if collections.is_empty():
            collections = None
        else:
            source = "store"
    if collections is None:
        collections = seed_work_state(viewer)
    return DashboardResponse(source=source, items=build_queue(collections))


@app.get("/api/pieces/{piece_id}", response_model=PieceDetailResponse, tags=["pieces"])
async def piece_detail(piece_id: str, viewer: str | None = None) -> PieceDetailResponse:
    """One piece across its whole lifecycle (cmw-ui-wireframes screen 2) — the piece-detail BFF
    reads this. Same store-or-seed fallback as ``/api/dashboard``, so a piece card's link target
    always resolves: the seed's deterministic slug-derived ids match across independent calls.
    """
    store: WorkStateStore | None = getattr(app.state, "work_state", None)
    found = None
    seeded = False
    if store is not None:
        work = await load_collections(store)
        if not work.is_empty():
            found = find_piece_collections(work, piece_id)
    if found is None:
        found = find_piece_collections(seed_work_state(viewer), piece_id)
        # Only a non-None hit on the seed fallback counts as seeded — a store piece that WAS
        # found above keeps seeded=False even though the fallback ran (it didn't match).
        seeded = found is not None
    if found is None:
        raise HTTPException(status_code=404, detail=f"no piece {piece_id!r}")
    content = getattr(app.state, "git_content", None)
    # ONE read of the piece's Git files serves both halves of the detail response: the readable
    # draft content and the sources.md the evidence trail is parsed from (app.evidence).
    files = content.read_piece_files(found.piece.slug) if content is not None else None
    draft_html = draft_content_from_files(files)
    sources_md = files.sources_md if files is not None else None
    return build_piece_detail(found, draft_html, sources_md=sources_md, seeded=seeded)
