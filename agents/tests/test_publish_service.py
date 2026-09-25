"""The publish service, end to end (finalized → published; docs/design.md's D13 note).

Chromium/Docs/S3 are faked (same acceptance bar as ``test_render_finalize_step.py``) — everything
else (revision read, editorial strip, semantic extraction, brand-token derivation, template
injection, immutable-key minting, Piece work-state update, and the full
``finalized -> published`` machine transition) runs for real against the real brain content.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.derivatives.quality import derivative_council_editors
from app.git import GitBrain, GitContentStore
from app.models import Council, EditorScore, Piece, PieceRole, PieceStage, ShareMode
from app.orchestration import JobRunner, PieceMachine, StepRegistry
from app.models.common import utcnow
from app.models.publication import ReleaseActor, TrivialEditWaiver
from app.publish.errors import (
    ApprovalInvalidated,
    DerivativeGateBlocked,
    NoRevisionToPublish,
    NotInFinalizedStage,
)
from app.publish.service import PublishService
from app.render.docs_export import DocRef
from app.render.pdf import PdfRenderError
from app.render.template import TemplateStore
from app.repositories import WorkStateStore


class FakeStorage:
    def __init__(self) -> None:
        self.puts: list[tuple[str, bytes, str]] = []

    async def put(self, key: str, body: bytes, *, content_type: str) -> str:
        self.puts.append((key, body, content_type))
        return f"https://fake-published-assets.example/{key}"


class FailingPdfRenderer:
    async def render(self, html: str) -> bytes:
        raise PdfRenderError("Chromium exploded")


class FakePdfRenderer:
    def __init__(self, content: bytes = b"%PDF-1.4 fake pdf bytes") -> None:
        self.content = content
        self.calls: list[str] = []

    async def render(self, html: str) -> bytes:
        self.calls.append(html)
        return self.content


class FakeDocsClient:
    def __init__(self) -> None:
        self.created: list[tuple[str, str, str]] = []
        self.parent_ids: list[str | None] = []
        self.shared: list[tuple[str, list[str] | None, str]] = []

    async def create_doc_from_html(
        self, title: str, html: str, *, description: str = "", parent_id: str | None = None
    ) -> DocRef:
        doc_id = f"doc-{len(self.created) + 1}"
        self.created.append((title, html, description))
        self.parent_ids.append(parent_id)
        return DocRef(doc_id=doc_id, url=f"https://docs.google.com/document/d/{doc_id}/edit")

    async def share_file(self, doc_id: str, *, emails: list[str] | None = None, role: str = "commenter") -> None:
        self.shared.append((doc_id, emails, role))


@pytest.fixture
def template_store(brain_repo: Path) -> TemplateStore:
    return TemplateStore(str(brain_repo))


def _machine(store: WorkStateStore) -> PieceMachine:
    return PieceMachine(store, JobRunner(store, StepRegistry()))


async def _piece(
    store: WorkStateStore,
    content: GitContentStore,
    *,
    slug: str = "token-vs-storage",
    voice: str = "demo-mira",
    stage: PieceStage = PieceStage.finalized,
    with_revision: bool = True,
) -> Piece:
    # Reuses the fixture brain's already-committed draft.html revision (same idiom as
    # test_review_mint.py's `_piece` helper) rather than committing a redundant no-op revision.
    latest_revision = None
    if with_revision:
        history = content.revision_history(slug, max_count=1)
        latest_revision = history[0].sha
    piece = Piece(slug=slug, voice=voice, stage=stage, latest_revision=latest_revision)
    return await store.pieces.insert(piece)


def _service(
    store: WorkStateStore,
    git_brain: GitBrain,
    content_store: GitContentStore,
    template_store: TemplateStore,
    *,
    storage: FakeStorage,
    docs_client: FakeDocsClient,
    pdf_renderer=None,
    drive_client=None,
    root_folder_name: str = "",
) -> PublishService:
    return PublishService(
        store,
        content_store,
        git_brain,
        template_store,
        storage,
        docs_client,
        _machine(store),
        pdf_renderer=pdf_renderer,
        drive_client=drive_client,
        root_folder_name=root_folder_name,
    )


@pytest.mark.asyncio
async def test_publish_happy_path_mints_immutable_release_1_and_flips_stage(
    store: WorkStateStore,
    git_brain: GitBrain,
    content_store: GitContentStore,
    template_store: TemplateStore,
) -> None:
    piece = await _piece(store, content_store)
    storage = FakeStorage()
    docs = FakeDocsClient()
    service = _service(
        store, git_brain, content_store, template_store, storage=storage, docs_client=docs,
        pdf_renderer=FakePdfRenderer(),
    )

    result = await service.publish(piece.id)

    assert PieceStage(result.piece.stage) == PieceStage.released
    assert result.piece.published_release == 1
    assert result.warnings == []

    html_key, html_body, html_ct = storage.puts[0]
    assert html_key == f"published/{piece.slug}/1/branded.html"
    assert html_ct == "text/html; charset=utf-8"
    assert "demo-dana-v1" in html_body.decode("utf-8")

    pdf_key, pdf_body, pdf_ct = storage.puts[1]
    assert pdf_key == f"published/{piece.slug}/1/branded.pdf"
    assert pdf_ct == "application/pdf"
    assert pdf_body == b"%PDF-1.4 fake pdf bytes"

    # Content safety: the editorial/GAP block must never reach a public artifact, in either the
    # S3 HTML or the externally-shared Doc.
    assert 'class="editorial"' not in html_body.decode("utf-8")
    assert 'class="editorial"' not in docs.created[0][1]
    # The published Doc gets the same professional Drive-friendly wrapper as finalize/review.
    assert "<!DOCTYPE html>" in docs.created[0][1]
    assert "font-family: 'Helvetica Neue', Arial, sans-serif" in docs.created[0][1]
    # Deliberately NOT the "DRAFT — not for external distribution" banner ShareMode.external
    # adds elsewhere (app.review.mint) — that would be false on genuinely published content.
    assert "DRAFT" not in docs.created[0][1]

    # Shared anyone-with-the-link/reader — matches the bucket's own generally-public policy.
    assert docs.shared == [("doc-1", None, "reader")]

    updated = await store.pieces.get(piece.id)
    assert updated is not None
    assert updated.published_release == 1
    assert updated.published_html_url == f"https://fake-published-assets.example/{html_key}"
    assert updated.published_pdf_url == f"https://fake-published-assets.example/{pdf_key}"
    assert updated.published_doc is not None
    assert updated.published_doc.doc_id == "doc-1"
    assert ShareMode(updated.published_doc.share_mode) == ShareMode.external
    assert updated.published_at is not None


@pytest.mark.asyncio
async def test_a_second_publish_mints_a_new_immutable_release_never_overwriting_the_first(
    store: WorkStateStore,
    git_brain: GitBrain,
    content_store: GitContentStore,
    template_store: TemplateStore,
) -> None:
    """Permanence: a re-authorization must not touch a prior release's key — an already-shared
    link keeps resolving. Repeatable from the terminal `released` stage: the second call appends
    release 2 without leaving the stage."""
    piece = await _piece(store, content_store)
    storage = FakeStorage()
    service = _service(
        store, git_brain, content_store, template_store, storage=storage, docs_client=FakeDocsClient(),
    )

    first = await service.publish(piece.id)
    assert first.piece.published_release == 1
    assert PieceStage(first.piece.stage) == PieceStage.released

    second = await service.publish(piece.id)

    assert second.piece.published_release == 2
    assert PieceStage(second.piece.stage) == PieceStage.released
    releases = await store.releases.by_piece(piece.id)
    assert [r.release_number for r in releases] == [1, 2]
    assert releases[0].revision == releases[1].revision
    first_key = storage.puts[0][0]
    second_key = storage.puts[1][0]
    assert first_key != second_key
    assert first_key == f"published/{piece.slug}/1/branded.html"
    assert second_key == f"published/{piece.slug}/2/branded.html"
    # Both keys are still present in the fake storage's write log — the first was never re-put
    # with different bytes (there is no overwrite call at all, only two distinct `put`s).
    assert len(storage.puts) == 2


@pytest.mark.asyncio
async def test_canonical_edit_after_approval_blocks_until_trivial_waiver(
    store: WorkStateStore,
    git_brain: GitBrain,
    content_store: GitContentStore,
    template_store: TemplateStore,
) -> None:
    piece = await _piece(store, content_store)
    assert piece.latest_revision is not None
    approved = piece.latest_revision
    service = _service(
        store, git_brain, content_store, template_store, storage=FakeStorage(), docs_client=FakeDocsClient(),
    )
    await store.pieces.update(
        piece.id, {"approved_revision": approved, "approved_at": utcnow()}
    )
    await store.pieces.update(piece.id, {"latest_revision": "edited-after-approval"})

    with pytest.raises(ApprovalInvalidated):
        await service.publish(piece.id)

    waiver = TrivialEditWaiver(
        piece_id=piece.id,
        from_revision=approved,
        to_revision="edited-after-approval",
        actor=ReleaseActor(subject_id="captain@example.com"),
        reason="typo in the heading",
        recorded_at=utcnow(),
    )
    await store.trivial_edit_waivers.insert(waiver)
    from app.release.approval import approval_status

    status = approval_status(
        approved_revision=approved,
        latest_revision="edited-after-approval",
        waivers=await store.trivial_edit_waivers.by_piece(piece.id),
    )
    assert status.valid is True


@pytest.mark.asyncio
async def test_publish_requires_finalized_stage(
    store: WorkStateStore,
    git_brain: GitBrain,
    content_store: GitContentStore,
    template_store: TemplateStore,
) -> None:
    piece = await _piece(store, content_store, stage=PieceStage.review)
    service = _service(
        store, git_brain, content_store, template_store, storage=FakeStorage(), docs_client=FakeDocsClient(),
    )

    with pytest.raises(NotInFinalizedStage):
        await service.publish(piece.id)


@pytest.mark.asyncio
async def test_publish_requires_a_committed_revision(
    store: WorkStateStore,
    git_brain: GitBrain,
    content_store: GitContentStore,
    template_store: TemplateStore,
) -> None:
    piece = await _piece(store, content_store, with_revision=False)
    service = _service(
        store, git_brain, content_store, template_store, storage=FakeStorage(), docs_client=FakeDocsClient(),
    )

    with pytest.raises(NoRevisionToPublish):
        await service.publish(piece.id)


@pytest.mark.asyncio
async def test_publish_unknown_piece_raises_key_error(
    store: WorkStateStore,
    git_brain: GitBrain,
    content_store: GitContentStore,
    template_store: TemplateStore,
) -> None:
    service = _service(
        store, git_brain, content_store, template_store, storage=FakeStorage(), docs_client=FakeDocsClient(),
    )

    with pytest.raises(KeyError):
        await service.publish("does-not-exist")


@pytest.mark.asyncio
async def test_a_missing_pdf_renderer_warns_and_still_publishes_html_and_doc(
    store: WorkStateStore,
    git_brain: GitBrain,
    content_store: GitContentStore,
    template_store: TemplateStore,
) -> None:
    piece = await _piece(store, content_store)
    storage = FakeStorage()
    service = _service(
        store, git_brain, content_store, template_store, storage=storage, docs_client=FakeDocsClient(),
        pdf_renderer=None,
    )

    result = await service.publish(piece.id)

    assert any("no PdfRenderer configured" in w for w in result.warnings)
    assert len(storage.puts) == 1  # html only
    assert result.piece.published_pdf_url is None
    assert result.piece.published_html_url is not None


@pytest.mark.asyncio
async def test_a_failing_pdf_renderer_warns_and_still_publishes(
    store: WorkStateStore,
    git_brain: GitBrain,
    content_store: GitContentStore,
    template_store: TemplateStore,
) -> None:
    piece = await _piece(store, content_store)
    service = _service(
        store, git_brain, content_store, template_store, storage=FakeStorage(), docs_client=FakeDocsClient(),
        pdf_renderer=FailingPdfRenderer(),
    )

    result = await service.publish(piece.id)

    assert any("Chromium exploded" in w for w in result.warnings)
    assert result.piece.published_pdf_url is None


# --- cmw-drive-piece-folders --------------------------------------------------------------------


class FakeDriveClient:
    def __init__(self) -> None:
        self.folders_created: list[tuple[str, str]] = []
        self.uploaded: list[tuple[str, bytes, str, str]] = []
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


@pytest.mark.asyncio
async def test_publish_with_no_root_configured_leaves_the_doc_at_the_root(
    store: WorkStateStore,
    git_brain: GitBrain,
    content_store: GitContentStore,
    template_store: TemplateStore,
) -> None:
    piece = await _piece(store, content_store)
    docs = FakeDocsClient()
    service = _service(
        store, git_brain, content_store, template_store,
        storage=FakeStorage(), docs_client=docs, pdf_renderer=FakePdfRenderer(),
    )

    result = await service.publish(piece.id)

    assert docs.parent_ids == [None]
    updated_piece = result.piece
    assert updated_piece.drive_folder_id is None
    assert updated_piece.published_drive_html is None
    assert updated_piece.published_drive_pdf is None


@pytest.mark.asyncio
async def test_publish_with_a_named_root_configured_uses_the_published_subfolder(
    store: WorkStateStore,
    git_brain: GitBrain,
    content_store: GitContentStore,
    template_store: TemplateStore,
) -> None:
    """Publish's own re-rendered copies land in the piece folder's `Published/` subfolder (never
    the finalize originals, moved or re-parented — this service never even sees those)."""
    piece = await _piece(store, content_store)
    docs = FakeDocsClient()
    drive_client = FakeDriveClient()
    service = _service(
        store, git_brain, content_store, template_store,
        storage=FakeStorage(), docs_client=docs, pdf_renderer=FakePdfRenderer(),
        drive_client=drive_client, root_folder_name="content-machine",
    )

    result = await service.publish(piece.id)

    # Root folder, the piece folder under it, then its Published child nested under that.
    assert len(drive_client.folders_created) == 3
    root_name, root_parent = drive_client.folders_created[0]
    piece_folder_name, piece_folder_parent = drive_client.folders_created[1]
    subfolder_name, subfolder_parent = drive_client.folders_created[2]
    assert (root_name, root_parent) == ("content-machine", "root")
    assert (piece_folder_name, piece_folder_parent) == (piece.slug, "folder-1")
    assert subfolder_name == "Published"

    stored = await store.pieces.get(piece.id)
    assert stored is not None
    assert subfolder_parent == stored.drive_folder_id
    published_folder_id = stored.drive_published_folder_id
    assert published_folder_id is not None

    uploaded_names = [u[0] for u in drive_client.uploaded]
    assert uploaded_names == ["branded.html", "branded.pdf"]
    assert all(u[3] == published_folder_id for u in drive_client.uploaded)

    # Published Drive files are shared reader/anyone, matching the published Doc's existing grant.
    shared_ids = {s[0] for s in docs.shared}
    assert result.piece.published_drive_html is not None
    assert result.piece.published_drive_pdf is not None
    assert result.piece.published_drive_html.file_id in shared_ids
    assert result.piece.published_drive_pdf.file_id in shared_ids
    for s in docs.shared:
        assert s[1:] == (None, "reader")

    # The Doc itself was parented into the SAME Published subfolder, not the piece folder root.
    assert docs.parent_ids == [published_folder_id]


# --- full machine integration: finalized -> released; repeatable numbered releases -----------


@pytest.mark.asyncio
async def test_a_released_piece_can_be_authorized_again_without_leaving_released(
    store: WorkStateStore,
    git_brain: GitBrain,
    content_store: GitContentStore,
    template_store: TemplateStore,
) -> None:
    piece = await _piece(store, content_store)
    service = _service(
        store, git_brain, content_store, template_store, storage=FakeStorage(), docs_client=FakeDocsClient(),
    )
    first = await service.publish(piece.id)
    assert PieceStage(first.piece.stage) == PieceStage.released
    second = await service.publish(piece.id)
    assert PieceStage(second.piece.stage) == PieceStage.released
    assert second.piece.published_release == 2
    # The bare machine gate is a no-op on an already-released piece (not a stage change).
    machine = _machine(store)
    stayed = await machine.publish(piece.id)
    assert PieceStage(stayed.stage) == PieceStage.released


# --- derivative quality bar: a native publishes only after clearing ITS OWN council ---------


async def _derivative_piece(
    store: WorkStateStore,
    content: GitContentStore,
    *,
    target: str = "linkedin-post",
) -> Piece:
    history = content.revision_history("token-vs-storage", max_count=1)
    return await store.pieces.insert(
        Piece(
            slug="token-vs-storage",
            voice="demo-mira",
            stage=PieceStage.finalized,
            latest_revision=history[0].sha,
            role=PieceRole.derivative,
            parent_piece_id="anchor-id",
            target=target,
        )
    )


async def _seed_council(
    store: WorkStateStore, piece: Piece, *, aggregate: float, revision: str | None = None
) -> Council:
    editors = list(derivative_council_editors(piece.target or ""))
    council = Council(
        piece_id=piece.id or "",
        revision=revision or piece.latest_revision,
        editor_scores=[EditorScore(editor=e, score=9.5) for e in editors],
        aggregate=aggregate,
    )
    council = await store.councils.insert(council)
    await store.pieces.update(piece.id, {"latest_council_id": council.id})
    return council


@pytest.mark.asyncio
async def test_publish_derivative_blocked_until_its_own_council_clears(
    store: WorkStateStore,
    git_brain: GitBrain,
    content_store: GitContentStore,
    template_store: TemplateStore,
) -> None:
    piece = await _derivative_piece(store, content_store)
    storage = FakeStorage()
    service = _service(
        store, git_brain, content_store, template_store, storage=storage, docs_client=FakeDocsClient(),
        pdf_renderer=FakePdfRenderer(),
    )

    # No council on record at all.
    with pytest.raises(DerivativeGateBlocked) as excinfo:
        await service.publish(piece.id)
    assert "no council on record" in str(excinfo.value)

    # A council below the 9/10 derivative bar still blocks.
    await _seed_council(store, piece, aggregate=8.4)
    with pytest.raises(DerivativeGateBlocked) as excinfo:
        await service.publish(piece.id)
    assert "below the 9 derivative bar" in str(excinfo.value)

    # Nothing external happened while the gate blocked.
    assert storage.puts == []


@pytest.mark.asyncio
async def test_publish_derivative_publishes_once_its_own_council_clears(
    store: WorkStateStore,
    git_brain: GitBrain,
    content_store: GitContentStore,
    template_store: TemplateStore,
) -> None:
    piece = await _derivative_piece(store, content_store)
    await _seed_council(store, piece, aggregate=9.2)
    storage = FakeStorage()
    service = _service(
        store, git_brain, content_store, template_store, storage=storage, docs_client=FakeDocsClient(),
        pdf_renderer=FakePdfRenderer(),
    )

    result = await service.publish(piece.id)

    assert PieceStage(result.piece.stage) == PieceStage.released
    assert result.piece.published_release == 1
    assert storage.puts  # the gate let the real mint run


@pytest.mark.asyncio
async def test_publish_derivative_blocked_when_council_scored_stale_revision(
    store: WorkStateStore,
    git_brain: GitBrain,
    content_store: GitContentStore,
    template_store: TemplateStore,
) -> None:
    piece = await _derivative_piece(store, content_store)
    await _seed_council(store, piece, aggregate=9.8, revision="some-older-revision")
    service = _service(
        store, git_brain, content_store, template_store, storage=FakeStorage(), docs_client=FakeDocsClient(),
        pdf_renderer=FakePdfRenderer(),
    )

    with pytest.raises(DerivativeGateBlocked) as excinfo:
        await service.publish(piece.id)
    assert "does not certify what would ship" in str(excinfo.value)


@pytest.mark.asyncio
async def test_unpublish_succeeds_when_one_artifact_already_missing(
    store: WorkStateStore,
    git_brain: GitBrain,
    content_store: GitContentStore,
    template_store: TemplateStore,
) -> None:
    """Unpublish must be resilient: one missing S3 object (or Drive folder) is normal; still succeeds for the rest."""
    from app.publish.service import UnpublishService
    from app.publish.storage import PublishStorage

    class MissingOneStorage(PublishStorage):
        async def put(self, key: str, body: bytes, *, content_type: str, acl: str = "public-read") -> str:
            return f"https://example.com/{key}"
        async def make_private(self, key: str) -> None:
            if "branded.pdf" in key:
                raise Exception("NoSuchKey simulated")  # one artifact already gone
            # html succeeds

    class FakeDocs:
        async def unshare_public(self, file_id: str) -> None:
            pass  # simulate Drive folder already deleted or permission gone

    piece = await _piece(store, content_store)
    # simulate published state with release
    await store.pieces.update(piece.id, {"published_release": 1, "slug": piece.slug, "drive_published_folder_id": "dummyfolder"})
    storage = MissingOneStorage()
    service = UnpublishService(store, storage, FakeDocs())
    result = await service.unpublish(piece.id)
    assert result.piece.id == piece.id
    assert any("branded.pdf" in w for w in result.warnings)  # recorded the skip
    assert not any("branded.html" in w for w in result.warnings)  # the other succeeded
