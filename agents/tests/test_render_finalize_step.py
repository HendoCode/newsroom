"""The finalize batch step, end to end (D13, Item 5; domain model §1.19).

Chromium/Docs are faked (per the acceptance bar "Chromium/Docs calls can be mocked/guarded") —
everything else (draft read, editorial strip, semantic extraction, brand-token derivation,
template injection, disk persistence, Piece work-state update, and the full
``finalizing -> finalized`` machine transition) runs for real against the real brain content.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.git import GitBrain, GitContentStore
from app.llm.budget import RunBudget
from app.models import Job, JobType, Piece, PieceStage
from app.orchestration import JobRunner, PieceMachine, StepContext, StepRegistry
from app.orchestration.retry import PermanentStepError
from app.render.docs_export import DocRef
from app.render.step import FinalizeStep
from app.render.template import TemplateStore
from app.repositories import WorkStateStore


class FakePdfRenderer:
    def __init__(self, content: bytes = b"%PDF-1.4 fake pdf bytes") -> None:
        self.content = content
        self.calls: list[str] = []

    async def render(self, html: str) -> bytes:
        self.calls.append(html)
        return self.content


class FailingPdfRenderer:
    async def render(self, html: str) -> bytes:
        from app.render.pdf import PdfRenderError

        raise PdfRenderError("Chromium exploded")


class FakeDocsClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []
        self.parent_ids: list[str | None] = []

    async def create_doc_from_html(
        self, title: str, html: str, *, description: str = "", parent_id: str | None = None
    ) -> DocRef:
        self.calls.append((title, html, description))
        self.parent_ids.append(parent_id)
        return DocRef(doc_id="doc-123", url="https://docs.google.com/document/d/doc-123/edit")


class FakeDriveClient:
    """cmw-drive-piece-folders: a fake DriveFolderClient — real Drive request-shape coverage
    lives in test_drive_http_client.py; this only proves FinalizeStep calls it correctly."""

    def __init__(self) -> None:
        self.folders_created: list[tuple[str, str]] = []
        self.uploaded: list[tuple[str, bytes, str, str]] = []  # (name, content, mime_type, parent_id)
        self._next_id = 1
        self._by_name: dict[str, str] = {}

    async def find_or_create_folder(self, name: str, *, parent_id: str = "root"):
        from app.drive.folder import DriveFileRef

        if name in self._by_name:
            file_id = self._by_name[name]
            return DriveFileRef(file_id=file_id, url=f"https://drive.google.com/drive/folders/{file_id}")
        return await self.create_folder(name, parent_id=parent_id)

    async def create_folder(self, name: str, *, parent_id: str):
        from app.drive.folder import DriveFileRef

        self.folders_created.append((name, parent_id))
        file_id = f"folder-{self._next_id}"
        self._next_id += 1
        self._by_name[name] = file_id
        return DriveFileRef(file_id=file_id, url=f"https://drive.google.com/drive/folders/{file_id}")

    async def upload_file(self, name: str, content: bytes, mime_type: str, *, parent_id: str):
        from app.drive.folder import DriveFileRef

        self.uploaded.append((name, content, mime_type, parent_id))
        file_id = f"file-{self._next_id}"
        self._next_id += 1
        return DriveFileRef(file_id=file_id, url=f"https://drive.google.com/file/d/{file_id}/view")


@pytest.fixture
def template_store(brain_repo: Path) -> TemplateStore:
    return TemplateStore(str(brain_repo))


async def _make_piece(store: WorkStateStore, *, stage: PieceStage = PieceStage.review) -> Piece:
    return await store.pieces.insert(
        Piece(slug="token-vs-storage", voice="demo-dana", stage=stage, latest_revision="rev-42")
    )


def _finalized_dir(content_store: GitContentStore, slug: str) -> Path:
    parts = [content_store.prefix, "drafts", slug, "finalized"] if content_store.prefix else [
        "drafts",
        slug,
        "finalized",
    ]
    return content_store.repo.abspath("/".join(parts))


def _ctx(
    piece: Piece,
    store: WorkStateStore,
    git_brain: GitBrain,
    content_store: GitContentStore,
    *,
    formats: list[str] | None = None,
) -> StepContext:
    job = Job(type=JobType.finalize, piece_id=piece.id, formats=formats)
    return StepContext(job=job, store=store, budget=RunBudget(), piece=piece, brain=git_brain, content=content_store)


# --- direct StepContext tests ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_produces_all_three_formats_by_default(
    store: WorkStateStore,
    git_brain: GitBrain,
    content_store: GitContentStore,
    template_store: TemplateStore,
) -> None:
    piece = await _make_piece(store)
    pdf_renderer = FakePdfRenderer()
    docs_client = FakeDocsClient()
    step = FinalizeStep(template_store=template_store, pdf_renderer=pdf_renderer, docs_client=docs_client)

    result = await step.run(_ctx(piece, store, git_brain, content_store))

    assert "produced html, pdf, doc" in result.notes[0]
    assert docs_client.calls and docs_client.calls[0][0] == (
        "The cheapest line on your AWS bill is the one you're arguing about"
    )
    assert "branded-header" not in docs_client.calls[0][1]
    # The clean semantic Doc gets a professional Drive-friendly wrapper (real headings/fonts).
    assert "<!DOCTYPE html>" in docs_client.calls[0][1]
    assert "font-family: 'Helvetica Neue', Arial, sans-serif" in docs_client.calls[0][1]
    assert "revision rev-42" in docs_client.calls[0][2]
    assert pdf_renderer.calls and "branded-header" in pdf_renderer.calls[0]

    updated = await store.pieces.get(piece.id)
    assert updated is not None
    assert updated.final_template_version == "demo-dana-v1"
    assert updated.final_rendered_at is not None
    assert updated.final_doc is not None
    assert updated.final_doc.doc_id == "doc-123"

    out_dir = _finalized_dir(content_store, piece.slug)
    branded_html = (out_dir / "branded.html").read_text(encoding="utf-8")
    assert "rev-42" in branded_html
    assert "demo-dana-v1" in branded_html
    assert (out_dir / "branded.pdf").read_bytes() == pdf_renderer.content
    assert '"doc_id": "doc-123"' in (out_dir / "google-doc.json").read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_formats_are_selectable(
    store: WorkStateStore,
    git_brain: GitBrain,
    content_store: GitContentStore,
    template_store: TemplateStore,
) -> None:
    piece = await _make_piece(store)
    step = FinalizeStep(template_store=template_store, pdf_renderer=None, docs_client=None)

    result = await step.run(_ctx(piece, store, git_brain, content_store, formats=["html"]))

    assert "produced html" in result.notes[0]
    out_dir = _finalized_dir(content_store, piece.slug)
    assert (out_dir / "branded.html").exists()
    assert not (out_dir / "branded.pdf").exists()
    assert not (out_dir / "google-doc.json").exists()

    updated = await store.pieces.get(piece.id)
    assert updated is not None and updated.final_doc is None


@pytest.mark.asyncio
async def test_a_missing_renderer_warns_and_skips_rather_than_failing(
    store: WorkStateStore,
    git_brain: GitBrain,
    content_store: GitContentStore,
    template_store: TemplateStore,
) -> None:
    """Mirrors Item 4's "one editor's failure completes-with-gap" — a partial failure to produce a
    requested format warns and continues, since at least one other format still succeeded."""
    piece = await _make_piece(store)
    step = FinalizeStep(template_store=template_store, pdf_renderer=None, docs_client=FakeDocsClient())

    result = await step.run(_ctx(piece, store, git_brain, content_store, formats=["html", "pdf", "doc"]))

    assert "produced html, doc" in result.notes[0]
    assert any("pdf skipped: no PdfRenderer configured" in note for note in result.notes)


@pytest.mark.asyncio
async def test_a_failing_renderer_warns_and_skips(
    store: WorkStateStore,
    git_brain: GitBrain,
    content_store: GitContentStore,
    template_store: TemplateStore,
) -> None:
    piece = await _make_piece(store)
    step = FinalizeStep(
        template_store=template_store, pdf_renderer=FailingPdfRenderer(), docs_client=FakeDocsClient()
    )

    result = await step.run(_ctx(piece, store, git_brain, content_store, formats=["pdf", "doc"]))

    assert any("pdf skipped: Chromium exploded" in note for note in result.notes)
    assert "produced doc" in result.notes[0]


@pytest.mark.asyncio
async def test_raises_when_zero_requested_formats_succeed(
    store: WorkStateStore,
    git_brain: GitBrain,
    content_store: GitContentStore,
    template_store: TemplateStore,
) -> None:
    piece = await _make_piece(store)
    step = FinalizeStep(template_store=template_store, pdf_renderer=None, docs_client=None)

    with pytest.raises(PermanentStepError):
        await step.run(_ctx(piece, store, git_brain, content_store, formats=["pdf"]))


@pytest.mark.asyncio
async def test_unknown_format_is_rejected(
    store: WorkStateStore,
    git_brain: GitBrain,
    content_store: GitContentStore,
    template_store: TemplateStore,
) -> None:
    piece = await _make_piece(store)
    step = FinalizeStep(template_store=template_store)

    with pytest.raises(ValueError, match="unknown finalize format"):
        await step.run(_ctx(piece, store, git_brain, content_store, formats=["epub"]))


# --- cmw-drive-piece-folders: the piece's Shared Drive folder ------------------------------


@pytest.mark.asyncio
async def test_with_no_root_configured_behavior_is_unchanged(
    store: WorkStateStore,
    git_brain: GitBrain,
    content_store: GitContentStore,
    template_store: TemplateStore,
) -> None:
    """The unset-configuration path this ticket must preserve: no drive_client, no
    root_folder_name — the Doc still gets created (at the Drive root, parent_id=None) and no
    drive_folder_id is ever written onto the Piece."""
    piece = await _make_piece(store)
    docs_client = FakeDocsClient()
    step = FinalizeStep(template_store=template_store, docs_client=docs_client, pdf_renderer=FakePdfRenderer())

    await step.run(_ctx(piece, store, git_brain, content_store))

    assert docs_client.parent_ids == [None]
    updated = await store.pieces.get(piece.id)
    assert updated is not None
    assert updated.drive_folder_id is None
    assert updated.final_drive_html is None
    assert updated.final_drive_pdf is None


@pytest.mark.asyncio
async def test_with_a_named_root_configured_the_folder_is_created_and_reused(
    store: WorkStateStore,
    git_brain: GitBrain,
    content_store: GitContentStore,
    template_store: TemplateStore,
) -> None:
    piece = await _make_piece(store)
    docs_client = FakeDocsClient()
    drive_client = FakeDriveClient()
    step = FinalizeStep(
        template_store=template_store,
        docs_client=docs_client,
        pdf_renderer=FakePdfRenderer(),
        drive_client=drive_client,
        root_folder_name="content-machine",
    )

    await step.run(_ctx(piece, store, git_brain, content_store))

    # Root folder first, then the piece folder parented under it.
    assert drive_client.folders_created == [("content-machine", "root"), (piece.slug, "folder-1")]
    after_run = await store.pieces.get(piece.id)
    assert after_run is not None
    folder_id = after_run.drive_folder_id
    assert docs_client.parent_ids == [folder_id]

    uploaded_names = [u[0] for u in drive_client.uploaded]
    assert uploaded_names == ["branded.html", "branded.pdf"]
    assert all(u[3] == folder_id for u in drive_client.uploaded)
    html_upload = drive_client.uploaded[0]
    assert html_upload[2] == "text/html"
    pdf_upload = drive_client.uploaded[1]
    assert pdf_upload[2] == "application/pdf"
    assert pdf_upload[1] == FakePdfRenderer().content

    assert after_run.drive_folder_url is not None
    assert after_run.final_drive_html is not None and after_run.final_drive_html.file_id is not None
    assert after_run.final_drive_pdf is not None and after_run.final_drive_pdf.file_id is not None

    # A second finalize run must reuse the same folder — never create a second one.
    await step.run(_ctx(after_run, store, git_brain, content_store))
    assert drive_client.folders_created == [("content-machine", "root"), (piece.slug, "folder-1")]


@pytest.mark.asyncio
async def test_a_failed_drive_upload_warns_and_skips_rather_than_failing_the_run(
    store: WorkStateStore,
    git_brain: GitBrain,
    content_store: GitContentStore,
    template_store: TemplateStore,
) -> None:
    from app.drive.folder import DriveFolderError

    class FailingDriveClient(FakeDriveClient):
        async def upload_file(self, name, content, mime_type, *, parent_id):
            raise DriveFolderError("Drive quota exceeded")

    piece = await _make_piece(store)
    step = FinalizeStep(
        template_store=template_store,
        docs_client=FakeDocsClient(),
        pdf_renderer=FakePdfRenderer(),
        drive_client=FailingDriveClient(),
        root_folder_name="content-machine",
    )

    result = await step.run(_ctx(piece, store, git_brain, content_store, formats=["html"]))

    assert "produced html" in result.notes[0]
    assert any("drive html upload skipped: Drive quota exceeded" in note for note in result.notes)


# --- full machine integration: finalizing -> finalized --------------------------------------


@pytest.mark.asyncio
async def test_machine_finalize_trigger_advances_review_to_finalized(
    store: WorkStateStore,
    git_brain: GitBrain,
    content_store: GitContentStore,
    template_store: TemplateStore,
) -> None:
    piece = await _make_piece(store, stage=PieceStage.review)
    registry = StepRegistry()
    registry.register(
        FinalizeStep(template_store=template_store, pdf_renderer=FakePdfRenderer(), docs_client=FakeDocsClient())
    )
    runner = JobRunner(store, registry, brain=git_brain, content=content_store)
    machine = PieceMachine(store, runner)

    result = await machine.finalize(piece.id)

    assert PieceStage(result.stage) == PieceStage.finalized
    assert result.final_doc is not None and result.final_doc.doc_id == "doc-123"
    assert result.final_template_version == "demo-dana-v1"
