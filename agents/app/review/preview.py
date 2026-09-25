"""The assisted "reviews done" ingest preview (open-decisions Item 7).

"The app first calls ``listComments`` on the Doc **and** diffs the Doc body against the frozen
revision, then shows a preview: '12 comments · 8 inline edits detected — fold these in?' so the
human sees exactly what will be ingested before committing." Read-only: nothing is classified,
applied, or persisted here — that only happens once "reviews done" actually fires
(:mod:`app.review.step`). Reuses :func:`app.review.collect.gather_raw_items` so the preview and the
real collect can never disagree about what counts as a comment or an edit.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.git.content import GitContentStore
from app.models import ReviewRound, ShareMode
from app.review.collect import gather_raw_items
from app.review.docs_client import ReviewDocsClient

_SAMPLE_LIMIT = 5


@dataclass(frozen=True)
class ReviewPreview:
    round_number: int
    comment_count: int
    edit_count: int
    no_changes: bool
    diff_degraded: bool  # True if edit-detection couldn't run (export failure) — comments still shown
    samples: list[str] = field(default_factory=list)


async def preview_round(
    docs_client: ReviewDocsClient, content: GitContentStore, round_: ReviewRound, *, slug: str
) -> ReviewPreview:
    """The "N comments · M edits — fold these in?" preview for ``round_``'s minted Doc."""
    doc_id = round_.doc.doc_id
    if not doc_id:
        return ReviewPreview(
            round_number=round_.round_number,
            comment_count=0,
            edit_count=0,
            no_changes=True,
            diff_degraded=False,
        )

    minted_html = content.read_revision(slug, round_.minted_from_revision)
    items, diff_ok = await gather_raw_items(
        docs_client,
        doc_id=doc_id,
        minted_from_html=minted_html,
        share_mode=ShareMode(round_.doc.share_mode),
    )
    comments = [i for i in items if i.comment_id is not None]
    edits = [i for i in items if i.comment_id is None]
    samples = [i.ask[:120] for i in items[:_SAMPLE_LIMIT]]

    return ReviewPreview(
        round_number=round_.round_number,
        comment_count=len(comments),
        edit_count=len(edits),
        no_changes=not items,
        diff_degraded=not diff_ok,
        samples=samples,
    )
