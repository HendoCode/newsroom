"""Tests for the piece-detail read-model (cmw-ui-wireframes screen 2).

Covers the join logic (``find_piece_collections`` filtering the shared ``WorkStateCollections``
down to one piece, against both the seed and a real store), the assembly (``build_piece_detail``:
mandatory-editor flagging, review-round/failure/lesson shaping, the synthesized activity log), the
Git draft read (``read_draft_content`` against the ``brain_repo`` fixture — a temp clone of the
fixture brain, ``conftest.py``), and the ``/api/pieces/{id}`` wire contract end to end.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import models as m
from app.dashboard import load_collections, seed_work_state
from app.git import GitContentStore, open_content_store
from app.main import app
from app.models import utcnow
from app.piece_detail import (
    PieceCollections,
    build_activity_log,
    build_piece_detail,
    find_piece_collections,
    read_draft_content,
)
from app.repositories import WorkStateStore

VIEWER = "me@example.com"


# --- find_piece_collections (the join) ------------------------------------------------------


def test_find_piece_collections_joins_seed_by_deterministic_id() -> None:
    seed = seed_work_state(VIEWER)
    found = find_piece_collections(seed, "seed-the-board-on-the-wall")
    assert found is not None
    assert found.piece.slug == "the-board-on-the-wall"
    assert len(found.councils) == 1 and found.councils[0].aggregate == 9.2
    assert len(found.review_rounds) == 1 and found.review_rounds[0].round_number == 2


def test_find_piece_collections_unknown_id_returns_none() -> None:
    assert find_piece_collections(seed_work_state(VIEWER), "no-such-piece") is None


def test_seed_piece_ids_are_deterministic_across_independent_calls() -> None:
    """A piece-detail fetch for the id a dashboard card just linked to must resolve against a
    LATER, independent seed call (there is no Mongo backing the seed, so it is regenerated fresh
    on every request) — guards the fix that replaced ``new_id()`` with a slug-derived id."""
    first = seed_work_state(VIEWER)
    second = seed_work_state(VIEWER)
    first_ids = {p.slug: p.id for p in first.pieces}
    second_ids = {p.slug: p.id for p in second.pieces}
    assert first_ids == second_ids


async def test_find_piece_collections_joins_over_real_store(store: WorkStateStore) -> None:
    piece = await store.pieces.insert(
        m.Piece(slug="s", voice="demo-mira", stage=m.PieceStage.review, owner="a@example.com")
    )
    await store.councils.insert(
        m.Council(
            piece_id=piece.id,
            revision="rev-1",
            round_number=1,
            editor_scores=[
                m.EditorScore(editor="slop-allergist", score=8.0),
                m.EditorScore(editor="voice-guardian", score=8.5),
            ],
            aggregate=8.5,
        )
    )
    await store.review_rounds.insert(
        m.ReviewRound(
            piece_id=piece.id,
            round_number=1,
            minted_from_revision="rev-1",
            doc=m.DocRef(url="https://docs.google.com/x", share_mode=m.ShareMode.external),
            opened_at=utcnow() - timedelta(days=2),
        )
    )
    await store.jobs.insert(
        m.Job(
            piece_id=piece.id,
            type=m.JobType.draft,
            status=m.JobStatus.failed,
            error=m.JobError(code="ceiling-exceeded", message="boom", retryable=False),
            triggered_by="a@example.com",
        )
    )

    work = await load_collections(store)
    found = find_piece_collections(work, piece.id)
    assert found is not None
    detail = build_piece_detail(found, draft_html=None)

    assert detail.council is not None and detail.council.aggregate == 8.5
    assert detail.review_round is not None
    assert detail.review_round.share_mode == "external"
    assert detail.review_round.doc_url == "https://docs.google.com/x"
    assert len(detail.failures) == 1
    assert detail.failures[0].code == "ceiling-exceeded"


# --- build_piece_detail assembly -------------------------------------------------------------


def _collections(**overrides) -> PieceCollections:
    piece = overrides.pop(
        "piece",
        m.Piece(id="p1", slug="p1", voice="demo-mira", stage=m.PieceStage.review, title="A piece"),
    )
    defaults = {"interviews": [], "jobs": [], "councils": [], "review_rounds": [], "lessons": []}
    defaults.update(overrides)
    return PieceCollections(piece=piece, **defaults)


def test_council_editor_scores_flag_mandatory_editors() -> None:
    collections = _collections(
        councils=[
            m.Council(
                piece_id="p1",
                revision="rev-1",
                round_number=1,
                aggregate=9.1,
                editor_scores=[
                    m.EditorScore(editor="slop-allergist", score=9.0),
                    m.EditorScore(editor="voice-guardian", score=9.4),
                    m.EditorScore(editor="specificity-auditor", score=10.0),
                ],
            )
        ]
    )
    detail = build_piece_detail(collections, draft_html=None)
    assert detail.council is not None
    mandatory = {s.editor: s.mandatory for s in detail.council.editor_scores}
    assert mandatory == {
        "slop-allergist": True,
        "voice-guardian": True,
        "specificity-auditor": False,
    }


def test_build_piece_detail_picks_the_latest_round_council() -> None:
    collections = _collections(
        councils=[
            m.Council(piece_id="p1", revision="rev-1", round_number=1, aggregate=7.0),
            m.Council(piece_id="p1", revision="rev-2", round_number=2, aggregate=9.2),
        ],
        review_rounds=[
            m.ReviewRound(piece_id="p1", round_number=1, minted_from_revision="rev-1"),
            m.ReviewRound(piece_id="p1", round_number=2, minted_from_revision="rev-2"),
        ],
    )
    detail = build_piece_detail(collections, draft_html=None)
    assert detail.council is not None and detail.council.round_number == 2
    assert detail.review_round is not None and detail.review_round.round_number == 2


def test_build_piece_detail_surfaces_all_review_rounds_with_routing_log() -> None:
    """The between-rounds routing log (piece-detail's own always-visible card): EVERY round, not
    just the latest, each carrying its own `routing_log` audit trail
    (`app.review.routing.route_non_fix_items`'s one-line-per-item record)."""
    collections = _collections(
        review_rounds=[
            m.ReviewRound(
                piece_id="p1",
                round_number=1,
                minted_from_revision="rev-1",
                status=m.ReviewRoundStatus.archived,
                routing_log=[
                    "info-gap routed to targeted interview iv-1: 'what about pricing?'",
                    "out-of-scope parked to Vault as spike sp-1: 'unrelated tangent'",
                ],
            ),
            m.ReviewRound(
                piece_id="p1",
                round_number=2,
                minted_from_revision="rev-2",
                status=m.ReviewRoundStatus.open,
            ),
        ],
    )
    detail = build_piece_detail(collections, draft_html=None)
    assert [r.round_number for r in detail.review_rounds] == [1, 2]
    assert detail.review_rounds[0].routing_log == [
        "info-gap routed to targeted interview iv-1: 'what about pricing?'",
        "out-of-scope parked to Vault as spike sp-1: 'unrelated tangent'",
    ]
    assert detail.review_rounds[1].routing_log == []
    # The singular convenience field still picks the latest round, unaffected by this addition.
    assert detail.review_round is not None and detail.review_round.round_number == 2


def test_build_piece_detail_carries_lessons_and_no_failures_when_clean() -> None:
    collections = _collections(
        lessons=[
            m.Lesson(
                voice="demo-mira",
                source_piece_id="p1",
                observed_change="x",
                generalizable_rule="y",
                status=m.LessonStatus.proposed,
            )
        ],
    )
    detail = build_piece_detail(collections, draft_html="<html>draft</html>")
    assert detail.draft_html == "<html>draft</html>"
    assert detail.failures == []
    assert len(detail.lessons) == 1 and detail.lessons[0].status == "proposed"


def test_build_piece_detail_surfaces_finalize_outputs() -> None:
    piece = m.Piece(
        id="p1",
        slug="p1",
        voice="demo-mira",
        stage=m.PieceStage.finalized,
        title="A piece",
        final_doc=m.DocRef(
            doc_id="doc-1", url="https://docs.google.com/x", share_mode=m.ShareMode.internal
        ),
        final_template_version="demo-dana/v3",
        final_rendered_at=utcnow(),
        drive_folder_url="https://drive.google.com/drive/folders/folder-1",
        final_drive_html=m.DriveFileRef(
            file_id="file-html-1", url="https://drive.google.com/file/d/file-html-1/view"
        ),
        final_drive_pdf=m.DriveFileRef(
            file_id="file-pdf-1", url="https://drive.google.com/file/d/file-pdf-1/view"
        ),
    )
    detail = build_piece_detail(_collections(piece=piece), draft_html=None)
    assert detail.final_doc is not None
    assert detail.final_doc.doc_id == "doc-1"
    assert detail.final_doc.url == "https://docs.google.com/x"
    assert detail.final_doc.share_mode == "internal"
    assert detail.final_template_version == "demo-dana/v3"
    assert detail.final_rendered_at is not None
    assert detail.drive_folder_url == "https://drive.google.com/drive/folders/folder-1"
    assert detail.final_drive_html is not None and detail.final_drive_html.file_id == "file-html-1"
    assert detail.final_drive_pdf is not None and detail.final_drive_pdf.file_id == "file-pdf-1"


def test_build_piece_detail_final_doc_none_before_finalize() -> None:
    detail = build_piece_detail(_collections(), draft_html=None)
    assert detail.final_doc is None
    assert detail.final_template_version is None
    assert detail.final_rendered_at is None
    assert detail.drive_folder_url is None
    assert detail.final_drive_html is None
    assert detail.final_drive_pdf is None


def test_build_piece_detail_surfaces_published_outputs() -> None:
    piece = m.Piece(
        id="p1",
        slug="p1",
        voice="demo-mira",
        stage=m.PieceStage.released,
        title="A piece",
        published_release=2,
        published_html_url="https://bucket.s3.amazonaws.com/published/p1/2/branded.html",
        published_pdf_url="https://bucket.s3.amazonaws.com/published/p1/2/branded.pdf",
        published_doc=m.DocRef(
            doc_id="pub-doc-1",
            url="https://docs.google.com/document/d/pub-doc-1/edit",
            share_mode=m.ShareMode.external,
        ),
        published_at=utcnow(),
        published_drive_html=m.DriveFileRef(
            file_id="pub-file-html-1", url="https://drive.google.com/file/d/pub-file-html-1/view"
        ),
        published_drive_pdf=m.DriveFileRef(
            file_id="pub-file-pdf-1", url="https://drive.google.com/file/d/pub-file-pdf-1/view"
        ),
    )
    detail = build_piece_detail(_collections(piece=piece), draft_html=None)
    assert detail.stage == "released"
    assert detail.published_release == 2
    assert detail.published_html_url == "https://bucket.s3.amazonaws.com/published/p1/2/branded.html"
    assert detail.published_pdf_url == "https://bucket.s3.amazonaws.com/published/p1/2/branded.pdf"
    assert detail.published_doc is not None
    assert detail.published_doc.doc_id == "pub-doc-1"
    assert detail.published_doc.share_mode == "external"
    assert detail.published_at is not None
    assert detail.published_drive_html is not None and detail.published_drive_html.file_id == "pub-file-html-1"
    assert detail.published_drive_pdf is not None and detail.published_drive_pdf.file_id == "pub-file-pdf-1"


def test_build_piece_detail_surfaces_archived_at() -> None:
    """An archived piece is still fully served here — only the dashboard queue excludes it
    (`app.dashboard.build_queue`); direct-by-id access is unaffected."""
    piece = m.Piece(
        id="p1",
        slug="p1",
        voice="demo-mira",
        stage=m.PieceStage.review,
        title="A piece",
        archived_at=utcnow(),
    )
    detail = build_piece_detail(_collections(piece=piece), draft_html=None)
    assert detail.archived_at is not None
    assert detail.stage == "review"  # archiving never touches stage


def test_build_piece_detail_archived_at_none_by_default() -> None:
    detail = build_piece_detail(_collections(), draft_html=None)
    assert detail.archived_at is None


def test_build_piece_detail_surfaces_staleness_timestamps() -> None:
    """cmw-staleness-timestamps: created_at/updated_at/last_human_touch_at all pass through, and
    a piece with no recorded human touch yet reports it as `None` rather than a machine
    timestamp — the whole point being that the two must never be conflated."""
    created = utcnow() - timedelta(days=10)
    updated = utcnow() - timedelta(hours=1)
    touched = utcnow() - timedelta(days=8)
    piece = m.Piece(
        id="p1",
        slug="p1",
        voice="demo-mira",
        stage=m.PieceStage.interviewing,
        title="A piece",
        created_at=created,
        updated_at=updated,
        last_human_touch_at=touched,
    )
    detail = build_piece_detail(_collections(piece=piece), draft_html=None)
    assert detail.created_at == created
    assert detail.updated_at == updated
    assert detail.last_human_touch_at == touched


def test_build_piece_detail_last_human_touch_at_none_when_never_touched() -> None:
    piece = m.Piece(id="p1", slug="p1", voice="demo-mira", stage=m.PieceStage.interviewing)
    detail = build_piece_detail(_collections(piece=piece), draft_html=None)
    assert detail.last_human_touch_at is None


def test_build_piece_detail_published_outputs_default_before_publish() -> None:
    detail = build_piece_detail(_collections(), draft_html=None)
    assert detail.published_release == 0
    assert detail.published_html_url is None
    assert detail.published_pdf_url is None
    assert detail.published_doc is None
    assert detail.published_at is None
    assert detail.published_drive_html is None
    assert detail.published_drive_pdf is None


def test_activity_log_sorts_newest_first_and_never_drops_undated_entries() -> None:
    collections = _collections(
        jobs=[
            m.Job(
                piece_id="p1",
                type=m.JobType.draft,
                status=m.JobStatus.succeeded,
                started_at=utcnow() - timedelta(days=2),
            )
        ],
        councils=[
            m.Council(
                piece_id="p1",
                revision="rev-1",
                round_number=1,
                aggregate=9.2,
                updated_at=utcnow() - timedelta(days=1),
            )
        ],
        interviews=[
            m.Interview(
                piece_id="p1",
                status=m.InterviewStatus.complete,
                about="scoping",
                updated_at=None,  # undated — must still surface, sorted last
            )
        ],
    )
    log = build_activity_log(collections)
    labels = [e.label for e in log]
    assert labels[0] == "council pass · round 1"  # 2026-07-29, newest
    assert labels[1] == "draft job ok"  # 2026-07-28
    assert labels[-1] == "interview marked complete"  # undated, never dropped


# --- read_draft_content (real Git brain) ------------------------------------------------------


def test_read_draft_content_reads_the_real_editorial_block(brain_repo: Path) -> None:
    content = open_content_store(brain_root=str(brain_repo))
    draft = read_draft_content(content, "rehearse-the-rollback")
    assert draft is not None
    assert 'class="editorial"' in draft
    assert "[GAP:" in draft  # the piece's own open annotation, verbatim from the brain


def test_read_draft_content_none_for_unknown_slug(brain_repo: Path) -> None:
    content = open_content_store(brain_root=str(brain_repo))
    assert read_draft_content(content, "no-such-piece") is None


def test_read_draft_content_none_when_content_store_unavailable() -> None:
    """``app.state.git_content`` is ``None`` whenever the Git brain isn't reachable (lifespan
    catches ``GitError`` there, not here) — the reader just degrades gracefully."""
    assert read_draft_content(None, "the-board-on-the-wall") is None


# --- /api/pieces/{id} wire contract -----------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_settings(monkeypatch: pytest.MonkeyPatch):
    from app.config import get_settings

    for var in ("MONGO_URL", "BRAIN_ROOT"):
        monkeypatch.delenv(var, raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_piece_detail_endpoint_seeds_and_reads_real_draft(
    monkeypatch: pytest.MonkeyPatch, brain_repo: Path
) -> None:
    monkeypatch.setenv("BRAIN_ROOT", str(brain_repo))
    with TestClient(app) as client:  # lifespan runs → no Mongo → seed path
        resp = client.get("/api/pieces/seed-the-board-on-the-wall", params={"viewer": VIEWER})
    assert resp.status_code == 200
    body = resp.json()
    assert body["slug"] == "the-board-on-the-wall"
    # The seed fallback is honest about provenance — the piece-detail screen renders its
    # "seeded data" badge off this flag (cmw-boss-facing-presentation).
    assert body["seeded"] is True
    assert body["stage"] == "review"
    assert body["council"]["aggregate"] == 9.2
    assert body["draft_html"] is not None and "editorial" in body["draft_html"]
    # `review_rounds` (plural, EVERY round) is real wire, not just the pure-function assembly
    # covered above — the between-rounds routing log's actual HTTP JSON shape.
    assert [r["round_number"] for r in body["review_rounds"]] == [2]
    assert body["review_rounds"][0]["routing_log"] == []
    # Evidence trail (claim chips + retrieval/source list) is real wire too. The demo brain's
    # provenance sheet is a transcript-traceability TABLE with no external URLs (its meta.json says
    # "No external citations by design"), so both halves of the drawer are honestly empty here —
    # the populated shapes are covered by test_piece_detail_endpoint_carries_claim_citations below
    # and by tests/test_evidence.py.
    assert body["evidence_citations"] == []
    assert body["evidence_sources"] == []


def _add_citation_shaped_draft(brain_repo: Path, slug: str) -> None:
    """Overwrite a piece's draft in the throwaway clone with the chip + sources shape.

    No masthead demo piece cites anything externally (by design), so the claim-citation wire
    contract needs a draft that does — seeded per test into the temp brain copy, exactly like the
    other synthetic folders in this suite, never into the checked-in snapshot.
    """
    folder = brain_repo / "drafts" / slug
    (folder / "draft.html").write_text(
        "<html><head><title>Rehearse the rollback</title></head><body><article>"
        '<p>The drill took two hours.<sup class="fn"><a href="#src1" id="r1">1</a></sup></p>'
        '<p>Six minutes of events were lost.<sup class="fn"><a href="#src2" id="r2">2</a></sup></p>'
        '<ol><li id="src1">Drill log. <a href="#r1">&#8617;</a></li>'
        '<li id="src2">Runbook. <a href="https://runbook.test/rollback">runbook.test/rollback</a> '
        '<a href="#r2">&#8617;</a></li></ol></article></body></html>',
        encoding="utf-8",
    )
    (folder / "sources.md").write_text(
        "# Sources & Handoff\n\n## Research citations\n"
        "- Drill duration confirmed in the log https://runbook.test/drill-log\n",
        encoding="utf-8",
    )
    GitContentStore(str(brain_repo)).repo.commit(
        [f"drafts/{slug}/draft.html", f"drafts/{slug}/sources.md"],
        f"content(drafts): citation-shaped {slug}",
        "test",
        "t@test",
    )


def test_piece_detail_endpoint_carries_claim_citations(
    monkeypatch: pytest.MonkeyPatch, brain_repo: Path
) -> None:
    """A draft that DOES author footnote chips must surface them as claim-level citations, plus the
    footnote + sources.md source entries behind them."""
    _add_citation_shaped_draft(brain_repo, "rehearse-the-rollback")
    monkeypatch.setenv("BRAIN_ROOT", str(brain_repo))
    with TestClient(app) as client:
        resp = client.get("/api/pieces/seed-rehearse-the-rollback", params={"viewer": VIEWER})
    assert resp.status_code == 200
    body = resp.json()
    assert [c["chip"] for c in body["evidence_citations"]] == ["1", "2"]
    assert body["evidence_citations"][0]["source_id"] == "src1"
    kinds = [s["kind"] for s in body["evidence_sources"]]
    assert kinds.count("footnote") == 2  # src1 + src2, the chips point at them
    assert "sources-md" in kinds  # the sources.md research citation fills the same drawer


def test_piece_detail_endpoint_unknown_id_404() -> None:
    with TestClient(app) as client:
        resp = client.get("/api/pieces/no-such-piece")
    assert resp.status_code == 404


def test_piece_detail_endpoint_never_leaks_secrets() -> None:
    with TestClient(app) as client:
        raw = client.get("/api/pieces/seed-the-board-on-the-wall").text.lower()
    for forbidden in ("api_key", "apikey", "mongo_url", "secret", "password"):
        assert forbidden not in raw
