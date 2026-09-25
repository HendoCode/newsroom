"""The shared editorial/GAP-block strip routine (domain model §1.11; D11; D13/Item 5).

A semantic ``draft.html`` revision ends with a trailing, not-for-publication block —

    <hr>
    <!-- ... EDITORIAL ANNOTATIONS banner comment ... -->
    <section class="editorial" ...> ... [GAP]/[NOTE]/[CLEARANCE] markers ... </section>

Two different callers need to remove exactly this block: an external Google-Doc share (D11, a
sibling ticket) and this finalize render (D13, Item 5). The domain model is explicit that this is
"the same strip D11 already applies for external shares, so it is one shared routine" — hence a
single, dependency-free function here rather than two copies.

Deliberately stdlib-only (``re``): the block shape is fixed by convention (one ``<section
class="editorial">`` near the end, never nested), so a full HTML parser would be more machinery for
no more correctness.
"""

from __future__ import annotations

import re

# Matches the trailing scaffolding as a whole: an optional `<hr>`, an optional HTML comment banner
# immediately before it, then the `<section class="editorial" ...>...</section>` element itself
# (class match is quote-agnostic and tolerant of extra classes/attributes). Non-greedy up to the
# first closing `</section>` — by convention the editorial block is never nested.
_EDITORIAL_BLOCK_RE = re.compile(
    r"(?:[ \t]*<hr\s*/?>\s*)?"
    r"(?:<!--(?:(?!-->).)*?-->\s*)?"
    r"""<section\b[^>]*\bclass\s*=\s*(["'])(?:(?!\1).)*\beditorial\b(?:(?!\1).)*\1[^>]*>"""
    r".*?"
    r"</section\s*>"
    r"\s*",
    re.IGNORECASE | re.DOTALL,
)


def strip_editorial_block(html: str) -> str:
    """Remove the trailing not-for-publication editorial/GAP block from a draft's HTML.

    Idempotent (a no-op on HTML that has already been stripped) and tolerant of the block being
    absent entirely. Everything else — the semantic content, any legitimate mid-document ``<hr>``
    separators — is left untouched, since the pattern only matches a ``<hr>``/comment that sits
    immediately (whitespace only) before the editorial ``<section>``.
    """
    return _EDITORIAL_BLOCK_RE.sub("", html)


def has_editorial_block(html: str) -> bool:
    """True if ``html`` still carries an editorial block (useful for a D11-style open-GAP warning)."""
    return _EDITORIAL_BLOCK_RE.search(html) is not None
