"""Brand-token derivation from ``visual-identity.md`` (D13, Item 5).

Run against the *same file shape* the brain uses, not a hand-copied CSS blob — the whole point of
"derived, never duplicated" is that this module tracks the actual file convention. The neutral demo
brain (``HendoCode/masthead``) ships no personal branding, so the identity parsed here is the
synthetic test stand-in (tests/synthetic_brand.py) read through the real ``GitBrain.read_voice``
path; a brain that carries no visual identity at all is covered by the fallback tests below.
"""

from __future__ import annotations

import pytest

from app.git import GitBrain
from app.render.brand import (
    BrandTokenError,
    derive_brand_tokens,
    derive_brand_tokens_safe,
    fetch_logo_data_uri,
)
from tests.synthetic_brand import SYNTH_LOGO_URL


def test_derives_tokens_from_the_visual_identity_file(branded_git_brain: GitBrain) -> None:
    visual_identity = branded_git_brain.read_voice("demo-dana").visual_identity
    assert visual_identity

    tokens = derive_brand_tokens(visual_identity)

    assert "--background:" in tokens.css_root_block
    assert "--primary:" in tokens.css_root_block
    assert "--font-serif:" in tokens.css_root_block
    assert "'Synth Serif'" in tokens.css_root_block
    assert "fonts.googleapis.com" in tokens.font_import_html
    assert tokens.font_import_html.startswith("<link")
    assert tokens.logo_url == SYNTH_LOGO_URL


@pytest.mark.parametrize(
    "broken_md",
    [
        "# no tokens here at all",
        "```css\n:root {\n  --background: 1 1% 1%;\n}\n```\n",  # tokens but no font vars/import/logo
        (
            "```css\n:root {\n --background: 1 1% 1%;\n}\n```\n"
            "```css\n--font-serif: serif;\n```\n"
        ),  # still missing the font <link> + logo
    ],
)
def test_raises_on_malformed_visual_identity(broken_md: str) -> None:
    with pytest.raises(BrandTokenError):
        derive_brand_tokens(broken_md)


@pytest.mark.asyncio
async def test_fetch_logo_data_uri_wraps_network_error() -> None:
    from app.render.brand import LogoFetchError

    with pytest.raises(LogoFetchError):
        # Loopback port with no listener refuses the connection immediately — proves the wrap
        # without depending on a real network fetch (or DNS) in a sandboxed test environment.
        await fetch_logo_data_uri("http://127.0.0.1:1/nonexistent-logo.png", timeout=2.0)


def test_missing_visual_identity_degrades_to_plain_tokens(git_brain: GitBrain) -> None:
    """The demo brain carries no ``visual-identity.md``: render plain, warn, never raise."""
    assert git_brain.read_voice("demo-dana").visual_identity is None

    tokens, warnings = derive_brand_tokens_safe(None)

    assert tokens.css_root_block == "" and tokens.font_import_html == "" and tokens.logo_url == ""
    assert any("plain fallback" in w for w in warnings)


def test_malformed_visual_identity_degrades_rather_than_raises() -> None:
    tokens, warnings = derive_brand_tokens_safe("# nothing parseable here")

    assert tokens.logo_url == ""
    assert any("malformed" in w for w in warnings)
