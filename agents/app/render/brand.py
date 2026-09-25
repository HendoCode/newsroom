"""Brand-token derivation from ``visual-identity.md`` (D13, Item 5; domain model §1.19).

The settled mechanism (open-decisions Item 5) is explicit: brand tokens are **derived from**
``demo-dana/visual-identity.md`` — the single source of truth in the Git brain — and never
hand-duplicated into the template. That file already ships a "ready-to-paste" ``:root`` CSS block,
a bare set of font-variable declarations, a Google Fonts ``<link>`` import, and the hosted logo URL
(see the brain's ``voice/demo-dana/visual-identity.md`` §2/§3/§6). This module is the
"small build/render step" Item 5 calls for: it extracts those fenced blocks with plain regexes (the
file's structure is fixed by convention, so a markdown parser would be more machinery for no more
correctness) — editing colors/fonts means editing ``visual-identity.md``, never this module.
"""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass

_TOKENS_RE = re.compile(r"```css\s*\n:root\s*\{(.*?)\}\s*\n```", re.DOTALL)
_FONT_VARS_RE = re.compile(r"```css\s*\n(--font-serif:.*?)\n```", re.DOTALL)
_FONT_IMPORT_RE = re.compile(
    r"```html\s*\n(<link[^>]*fonts\.googleapis\.com[^>]*>)\s*\n```", re.DOTALL
)
_LOGO_RE = re.compile(r"\*\*Full logo:\*\*\s*`([^`]+)`")


class BrandTokenError(RuntimeError):
    """``visual-identity.md`` is missing a fenced block this derivation expects."""


@dataclass(frozen=True)
class BrandTokens:
    """The derived, template-ready brand tokens (never hand-duplicated — Item 5)."""

    css_root_block: str  # the `:root { ... }` declarations (colors + font variables), unwrapped
    font_import_html: str  # the Google Fonts `<link ...>` tag
    logo_url: str  # the hosted logo URL


def derive_brand_tokens(visual_identity_md: str) -> BrandTokens:
    """Parse the ready-to-paste tokens, font variables, font import, and logo URL.

    Raises :class:`BrandTokenError` if any expected fenced block is missing — a loud failure is
    preferable to silently rendering with default/missing brand colors.
    """
    tokens_match = _TOKENS_RE.search(visual_identity_md)
    if not tokens_match:
        raise BrandTokenError("no ready-to-paste `:root { ... }` CSS block found in visual-identity.md")
    font_vars_match = _FONT_VARS_RE.search(visual_identity_md)
    if not font_vars_match:
        raise BrandTokenError("no `--font-serif/--font-sans/--font-mono` block found in visual-identity.md")
    font_import_match = _FONT_IMPORT_RE.search(visual_identity_md)
    if not font_import_match:
        raise BrandTokenError("no Google Fonts <link> import found in visual-identity.md")
    logo_match = _LOGO_RE.search(visual_identity_md)
    if not logo_match:
        raise BrandTokenError("no '**Full logo:** `<url>`' line found in visual-identity.md")

    css_root_block = f"{tokens_match.group(1).strip()}\n{font_vars_match.group(1).strip()}"
    return BrandTokens(
        css_root_block=css_root_block,
        font_import_html=font_import_match.group(1).strip(),
        logo_url=logo_match.group(1).strip(),
    )


def _plain_brand_tokens() -> BrandTokens:
    """A safe, minimal fallback when no usable visual identity is available.

    The render still produces an HTML page; it simply won't carry custom colors,
    fonts, or a logo. Callers should warn that the output is unbranded.
    """
    return BrandTokens(css_root_block="", font_import_html="", logo_url="")


def derive_brand_tokens_safe(visual_identity_md: str | None) -> tuple[BrandTokens, list[str]]:
    """Derive brand tokens from ``visual-identity.md`` if possible; otherwise fall back to
    plain tokens and return a warning explaining why.

    Never raises — a missing/malformed visual identity is a degradation, not a fatal error.
    """
    if not visual_identity_md:
        return _plain_brand_tokens(), ["visual identity unavailable; rendering with plain fallback"]
    try:
        return derive_brand_tokens(visual_identity_md), []
    except BrandTokenError as exc:
        return _plain_brand_tokens(), [f"visual identity malformed ({exc}); rendering with plain fallback"]


class LogoFetchError(RuntimeError):
    """The hosted logo could not be fetched/inlined. Callers should warn and fall back to the
    remote URL rather than block the render (§5 "warns, does not block")."""


async def fetch_logo_data_uri(url: str, *, timeout: float = 15.0) -> str:
    """Fetch the hosted brand logo and return it as a ``data:`` URI (base64-encoded).

    D13/Item 5: "fetch-and-inline it as base64 so the artifact stands alone" — the branded HTML/PDF
    must be self-contained/portable, matching the agent's own self-contained-artifact discipline.
    """
    import httpx

    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise LogoFetchError(f"could not fetch logo from {url!r}: {exc}") from exc
    mime = resp.headers.get("content-type", "image/webp").split(";")[0].strip() or "image/webp"
    encoded = base64.b64encode(resp.content).decode("ascii")
    return f"data:{mime};base64,{encoded}"
