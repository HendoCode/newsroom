"""COLLECT: pull every comment + inline edit into the piece's feedback inbox (feedback-intake.md).

"COLLECT: pull all input into ``drafts/<piece>/feedback.md``, one row per item" — here the row is
a :class:`RawFeedbackItem`, the pre-classification material :mod:`app.review.classify` turns into
typed :class:`~app.models.FeedbackItem` records. Two sources, both gathered with no filtering (no
silent drops applies to collection too):

- **Comments** — every :class:`~app.review.docs_client.CommentThread` from ``listComments``,
  verbatim (a resolved thread is still collected; ``resolved`` is a Docs-UI affordance, not this
  system's own routing status).
- **Inline edits** — a structural HTML diff of the Doc body against the frozen revision it was
  minted from (cmw-reviewer-can-edit-doc / decision-structure-intake.md: headings, paragraph
  breaks, and bold/italic/underline must survive into the description, not just changed text — see
  :mod:`app.review.structure` for why that needs HTML, not plain text, and what was verified
  empirically about the round trip). Best-effort: a diff that can't be computed (export failure,
  transient network) drops only the edit-detection half, never the comments, and never fails the
  caller — see :func:`gather_raw_items`.

The diff base must match what actually got minted, not what a caller assumes got minted
(cmw-internal-round-editorial-diff-asymmetry): an internal round's Doc genuinely keeps the trailing
editorial block (its wrapping ``<section>`` doesn't survive the round trip, but its child
heading/paragraph elements do — :mod:`app.review.structure`), while an external round's Doc never
had it at all (:mod:`app.review.mint` strips it before upload, D11). ``diff_edits``/``diff_blocks``
themselves stay a pure block-vs-block diff with no editorial-block awareness; :func:`gather_raw_items`
reconstructs the correct original side via :func:`app.review.mint.render_for_share_mode` — the exact
same transform ``ReviewMintService.mint`` applied — so the two can never drift out of sync again the
way they did before this fix (unconditional stripping on the Git side, none on the Doc side).

The same reconstruction is not enough for the DRAFT banner (cmw-phantom-edits-from-doc-roundtrip):
it is authored as a non-block ``<div>`` (see :mod:`app.review.mint`), so it never becomes a
:class:`~app.review.structure.Block` on our own reconstructed side at all — yet Drive's HTML-to-
Docs conversion turns it into a real ``<p>`` on the exported Doc (confirmed live), which *does*
extract as a block. Re-running ``render_for_share_mode`` can't fix this, since the two sides are
genuinely different HTML by this point, not just differently stripped. :func:`gather_raw_items`
drops any extracted block matching :data:`app.review.mint.DRAFT_BANNER_TEXT` from both sides before
diffing — the block-list equivalent of excluding it from the diff base entirely, the same
treatment the (structurally different) editorial block already gets.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass

from app.models import ShareMode
from app.review.docs_client import ReviewDocsClient
from app.review.mint import DRAFT_BANNER_TEXT, render_for_share_mode
from app.review.structure import Block, extract_blocks, heading_label


@dataclass(frozen=True)
class RawFeedbackItem:
    """One uncategorized review input — the material :mod:`app.review.classify` classifies."""

    ask: str
    reviewer: str | None = None
    location: str | None = None
    channel: str = "google-docs"
    comment_id: str | None = None  # set only for a Docs comment — lets us reply_to_comment later
    # Set only for a diff-detected edit (channel="google-docs-edit"): the raw before/after text of
    # this changed span, alongside `ask`'s human-readable summary of the same. A lesson proposal
    # (app.lessons.service.LessonsService.propose_from_review_edits) needs the clean text pair, not
    # `ask`'s repr-quoted phrasing ("reviewer changed 'X' to 'Y'") reparsed back apart.
    before: str | None = None
    after: str | None = None


async def collect_comments(docs_client: ReviewDocsClient, doc_id: str) -> list[RawFeedbackItem]:
    threads = await docs_client.list_comments(doc_id)
    return [
        RawFeedbackItem(
            ask=t.content,
            reviewer=t.author,
            location=t.quoted_text,
            channel="google-docs",
            comment_id=t.comment_id,
        )
        for t in threads
    ]


def _label_and_text(block: Block) -> str:
    return f"[{heading_label(block.kind)}] {block.text!r}"


def _describe_block_pair(old: Block, new: Block) -> str | None:
    """One old block became one new block — describe every dimension that changed (kind, text,
    emphasis), not just the text: "the model can only act on what the item tells it" (Hendo).
    Returns ``None`` if nothing actually differs (the ``equal``-opcode pairwise recheck in
    :func:`diff_edits` calls this speculatively, since matching by text alone can't rule out a
    same-text kind/emphasis change)."""
    fragments: list[str] = []
    if old.kind != new.kind:
        # Always names the (possibly text-unchanged) block, since a pure kind change with no
        # text-changed fragment below would otherwise tell the model nothing about *which* text.
        fragments.append(
            f"converted {new.text!r} back to a plain paragraph"
            if new.kind == "p"
            else f"marked {new.text!r} as {heading_label(new.kind)}"
        )
    if old.text != new.text:
        if not old.text:
            fragments.append(f"added {new.text!r}")
        elif not new.text:
            fragments.append(f"removed {old.text!r}")
        else:
            fragments.append(f"changed {old.text!r} to {new.text!r}")
    for span in new.emphasis:
        if span not in old.emphasis:
            text, bold, italic, underline = span
            labels = "/".join(
                label for label, flag in (("bold", bold), ("italic", italic), ("underline", underline)) if flag
            )
            fragments.append(f"emphasized {text!r} as {labels}")
    for span in old.emphasis:
        if span not in new.emphasis:
            fragments.append(f"removed emphasis from {span[0]!r}")
    if not fragments:
        return None
    return "reviewer " + "; ".join(fragments)


def _describe_span(old_blocks: list[Block], new_blocks: list[Block]) -> str | None:
    """An insert/delete/replace opcode spanning any number of blocks on either side. A clean
    one-to-one span gets the full structural treatment above; anything else (a split, a merge, a
    multi-block replace) is described as a kind-tagged list on each side — e.g. "reviewer changed
    [paragraph] 'X Y' to [Heading 2] 'X'; [paragraph] 'Y'" already says a new heading was added and
    body text follows it, which is exactly the signal Hendo asked for, without a bespoke
    split/merge detector."""
    if len(old_blocks) == 1 and len(new_blocks) == 1:
        return _describe_block_pair(old_blocks[0], new_blocks[0])
    old_desc = "; ".join(_label_and_text(b) for b in old_blocks)
    new_desc = "; ".join(_label_and_text(b) for b in new_blocks)
    if not old_blocks:
        return f"reviewer added: {new_desc}"
    if not new_blocks:
        return f"reviewer removed: {old_desc}"
    return f"reviewer changed {old_desc} to {new_desc}"


def diff_edits(original_html: str, current_html: str) -> list[RawFeedbackItem]:
    """Block-level structural diff (cmw-reviewer-can-edit-doc / decision-structure-intake.md):
    diffs HTML against HTML — via :mod:`app.review.structure` — so a heading, a paragraph split,
    or a bold/italic/underline emphasis survives into the description handed to the model. A
    flattened plain-text diff (the previous implementation) destroyed all three before the diff
    ever ran.

    Purely mechanical — no editorial-block/banner awareness. ``original_html`` must already be
    shaped like whatever actually got minted (see :func:`gather_raw_items`/
    :func:`app.review.mint.render_for_share_mode`); this function never assumes a strip."""
    return diff_blocks(extract_blocks(original_html), extract_blocks(current_html))


def diff_blocks(original_blocks: list[Block], current_blocks: list[Block]) -> list[RawFeedbackItem]:
    """The same structural diff as :func:`diff_edits`, over already-extracted blocks — lets a
    caller (:func:`gather_raw_items`) filter blocks (e.g. the DRAFT banner) before diffing rather
    than after, since filtering post-diff would require re-deriving which raw items came from the
    filtered block(s). Each changed block/span becomes one raw item — never anchored to a comment
    (``comment_id=None``), so it can't be replied to, only routed/applied."""
    matcher = difflib.SequenceMatcher(
        a=[b.text for b in original_blocks], b=[b.text for b in current_blocks], autojunk=False
    )

    items: list[RawFeedbackItem] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            # Text matched, but an "equal" opcode always pairs 1:1 by position — kind/emphasis
            # might still differ (e.g. a same-text paragraph marked as a heading).
            for k in range(i2 - i1):
                old, new = original_blocks[i1 + k], current_blocks[j1 + k]
                desc = _describe_block_pair(old, new)
                if desc:
                    items.append(
                        RawFeedbackItem(
                            ask=desc,
                            location=f"block {i1 + k + 1}",
                            channel="google-docs-edit",
                            before=old.text,
                            after=new.text,
                        )
                    )
            continue

        old_blocks = original_blocks[i1:i2]
        new_blocks = current_blocks[j1:j2]
        desc = _describe_span(old_blocks, new_blocks)
        if desc:
            items.append(
                RawFeedbackItem(
                    ask=desc,
                    location=f"near block {i1 + 1}",
                    channel="google-docs-edit",
                    before=" ".join(b.text for b in old_blocks),
                    after=" ".join(b.text for b in new_blocks),
                )
            )
    return items


async def gather_raw_items(
    docs_client: ReviewDocsClient,
    *,
    doc_id: str,
    minted_from_html: str,
    share_mode: ShareMode,
) -> tuple[list[RawFeedbackItem], bool]:
    """Comments (always) + diff-detected edits (best-effort). Returns ``(items, diff_ok)`` — a
    caller (the preview, the incorporate step) can note when the edit-detection half degraded
    without ever losing the comments it did manage to collect.

    ``share_mode`` reconstructs the diff's original side to match what actually got minted for
    this round (:func:`app.review.mint.render_for_share_mode`) — required, not defaulted, since
    every real round has a real share mode and guessing wrong here is exactly the bug this
    parameter exists to prevent."""
    comments = await collect_comments(docs_client, doc_id)
    diff_ok = True
    edits: list[RawFeedbackItem] = []
    try:
        current_html = await docs_client.get_document_html(doc_id)
        original_html = render_for_share_mode(minted_from_html, share_mode)
        original_blocks = _drop_draft_banner(extract_blocks(original_html))
        current_blocks = _drop_draft_banner(extract_blocks(current_html))
        edits = diff_blocks(original_blocks, current_blocks)
    except Exception:  # noqa: BLE001 — best-effort enrichment, never fails the collect
        diff_ok = False
    return [*comments, *edits], diff_ok


def _drop_draft_banner(blocks: list[Block]) -> list[Block]:
    """Drop the DRAFT banner block, if present — it is Google's own conversion artifact (a non-
    block ``<div>`` becoming a real ``<p>`` on export), never real draft content, so it is excluded
    from both sides rather than read as a reviewer addition/removal (cmw-phantom-edits-from-doc-
    roundtrip)."""
    return [b for b in blocks if b.text != DRAFT_BANNER_TEXT]
