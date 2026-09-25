"""Semantic-content extraction from a (stripped) draft.html (D13, Item 5).

After :func:`app.render.editorial.strip_editorial_block` removes the not-for-publication tail, the
finalize template needs two things out of the remaining document: the ``<title>`` and the
publishable body markup (``<h1>/<h2>/<p>/<figure>``, inline SVGs) to inject into the branded
template's content slot.

Real pieces are not consistent about wrapping their content in ``<article>`` — compare
``drafts/token-vs-storage/draft.html`` (wraps in ``<article>``) with ``drafts/aws-gsi-faq/draft.html``
(writes directly under ``<body>``, no ``<article>`` tag). So the extraction prefers an ``<article>``
element when present and otherwise falls back to the whole ``<body>`` interior — stdlib ``re`` only,
no new HTML-parsing dependency for what is, in both real shapes, a single well-formed element.
"""

from __future__ import annotations

import html as _html
import re

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title\s*>", re.IGNORECASE | re.DOTALL)
_BODY_RE = re.compile(r"<body\b[^>]*>(.*)</body\s*>", re.IGNORECASE | re.DOTALL)
_ARTICLE_RE = re.compile(r"<article\b[^>]*>.*?</article\s*>", re.IGNORECASE | re.DOTALL)


def extract_title(html: str) -> str | None:
    """The document's ``<title>`` text, HTML-unescaped and whitespace-trimmed (or ``None``)."""
    match = _TITLE_RE.search(html)
    if not match:
        return None
    text = _html.unescape(match.group(1)).strip()
    return text or None


def extract_semantic_body(html: str) -> str:
    """The publishable content markup: the ``<article>`` element if present, else the whole
    ``<body>`` interior, else (a document fragment with neither) the input as-is. Callers are
    expected to have already run :func:`app.render.editorial.strip_editorial_block` first."""
    body_match = _BODY_RE.search(html)
    scope = body_match.group(1) if body_match else html
    article_match = _ARTICLE_RE.search(scope)
    if article_match:
        return article_match.group(0).strip()
    return scope.strip()
