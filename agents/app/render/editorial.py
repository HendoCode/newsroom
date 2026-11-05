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

# The editorial ``<section>`` opener: class match is quote-agnostic and tolerant of extra
# classes/attributes.
_SECTION_OPEN_RE = re.compile(
    r"""<section\b[^>]*\bclass\s*=\s*(["'])(?:(?!\1).)*\beditorial\b(?:(?!\1).)*\1[^>]*>""",
    re.IGNORECASE,
)
_SECTION_CLOSE_RE = re.compile(r"</section\s*>", re.IGNORECASE)
_COMMENT_RE = re.compile(r"<!--(?:(?!-->).)*?-->", re.DOTALL)
# The scaffolding that may sit immediately (whitespace only) before the section: a banner comment
# and/or an `<hr>` divider. Anchored at the end of the prefix, so a divider elsewhere in the
# document is never swallowed.
_PREFIX_RE = re.compile(r"(?:<!--(?:(?!-->).)*?-->)?\s*(?:<hr\s*/?>)?\s*$", re.DOTALL)


def _in_comment(pos: int, spans: list[tuple[int, int]]) -> bool:
    return any(start <= pos < end for start, end in spans)


def _editorial_spans(html: str) -> list[tuple[int, int]]:
    """``(start, end)`` of every real editorial block, including its ``<hr>``/banner scaffolding.

    An occurrence quoted **inside an HTML comment** is not markup: the demo brain's own
    ``draft.html`` header comment documents this very convention by name, and matching that
    literal once consumed the whole document — from the comment to the first real
    ``</section>`` — silently deleting the article instead of the annotations.
    """
    comments = [(m.start(), m.end()) for m in _COMMENT_RE.finditer(html)]
    spans: list[tuple[int, int]] = []
    for opener in _SECTION_OPEN_RE.finditer(html):
        if _in_comment(opener.start(), comments):
            continue
        closer = _SECTION_CLOSE_RE.search(html, opener.end())
        if closer is None:
            continue  # malformed; leave the document untouched rather than guess an end
        prefix = html[: opener.start()]
        scaffold = _PREFIX_RE.search(prefix)
        start = scaffold.start() if scaffold else opener.start()
        end = closer.end()
        trailing = re.match(r"\s*", html[end:])
        assert trailing is not None
        end += trailing.end()
        spans.append((start, end))
    return spans


def strip_editorial_block(html: str) -> str:
    """Remove the trailing not-for-publication editorial/GAP block from a draft's HTML.

    Idempotent (a no-op on HTML that has already been stripped) and tolerant of the block being
    absent entirely. Everything else — the semantic content, any legitimate mid-document ``<hr>``
    separators, and any prose that merely *quotes* the convention — is left untouched.
    """
    out = html
    for start, end in reversed(_editorial_spans(html)):
        out = out[:start] + out[end:]
    return out


def has_editorial_block(html: str) -> bool:
    """True if ``html`` still carries an editorial block (useful for a D11-style open-GAP warning)."""
    return bool(_editorial_spans(html))
