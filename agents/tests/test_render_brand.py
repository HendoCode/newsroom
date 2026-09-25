"""Brand-token derivation from ``visual-identity.md`` (D13, Item 5).

Run against the *real* file, not a hand-copied fixture — the whole point of "derived, never
duplicated" is that this module tracks the actual brain content.
"""

from __future__ import annotations

import pytest

from app.git import GitBrain
from app.render.brand import BrandTokenError, derive_brand_tokens, fetch_logo_data_uri


def test_derives_tokens_from_real_visual_identity(git_brain: GitBrain) -> None:
    visual_identity = git_brain.read_voice("demo-dana").visual_identity
    assert visual_identity

    tokens = derive_brand_tokens(visual_identity)

    assert "--background:" in tokens.css_root_block
    assert "--primary:" in tokens.css_root_block
    assert "--font-serif:" in tokens.css_root_block
    assert "'Josefin Sans'" in tokens.css_root_block
    assert "fonts.googleapis.com" in tokens.font_import_html
    assert tokens.font_import_html.startswith("<link")
    assert tokens.logo_url == "https://hendocode.com/"


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
