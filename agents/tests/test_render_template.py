"""Versioned branded template: read (with Git provenance) + slot injection (D13, Item 5).

The brain repo is the neutral demo suite and ships **no** branding, so the branded path is covered
against ``branded_brain_repo`` (conftest.py) — the temp git repo seeded with a copy of the brain plus
the synthetic stand-in ``templates/branded/demo-dana-v1.html`` (tests/synthetic_brand.py). Seeding it
through Git is the point: it proves the template is genuinely versioned in the same store as
everything else, with a real commit sha. The unbranded brain is covered by the degradation tests
below.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.render.template import (
    PLAIN_TEMPLATE_VERSION,
    TEAM_VOICE_TEMPLATE_VERSION,
    TemplateNotFound,
    TemplateStore,
    render_branded_html,
)
from tests.synthetic_brand import SYNTH_BRAND_MARKER


@pytest.fixture
def template_store(brain_repo: Path) -> TemplateStore:
    """Against the brain as it actually ships today: no branded template at all."""
    return TemplateStore(str(brain_repo))


@pytest.fixture
def branded_template_store(branded_brain_repo: Path) -> TemplateStore:
    return TemplateStore(str(branded_brain_repo))


def test_reads_the_versioned_template(branded_template_store: TemplateStore) -> None:
    template = branded_template_store.read()

    assert template.version == TEAM_VOICE_TEMPLATE_VERSION == "demo-dana-v1"
    assert template.path.endswith("templates/branded/demo-dana-v1.html")
    assert "{{ARTICLE_HTML}}" in template.html
    assert "{{TOKENS_CSS}}" in template.html
    # A real commit sha — proves Git *is* the versioning here too (D2/D4), not a bare file read.
    assert template.sha and len(template.sha) == 40


def test_unknown_version_raises(template_store: TemplateStore) -> None:
    with pytest.raises(TemplateNotFound):
        template_store.read("demo-dana-v2")


def test_missing_template_file_raises(tmp_path: Path) -> None:
    import subprocess

    empty_repo = tmp_path / "empty"
    empty_repo.mkdir()
    subprocess.run(["git", "init", "-q", str(empty_repo)], check=True)
    store = TemplateStore(str(empty_repo))
    with pytest.raises(TemplateNotFound):
        store.read()


def test_read_or_plain_degrades_when_the_brain_ships_no_template(
    template_store: TemplateStore,
) -> None:
    """The neutral demo brain has no ``templates/branded/`` — finalize must warn, not fail."""
    template, warnings = template_store.read_or_plain()

    assert template.version == PLAIN_TEMPLATE_VERSION == "plain-v1"
    assert "{{ARTICLE_HTML}}" in template.html
    assert template.sha is None
    assert any("branded template not found" in w for w in warnings)


def test_read_or_plain_still_raises_on_an_unknown_version(template_store: TemplateStore) -> None:
    """Degradation is for a missing asset, never for a caller bug in the version label."""
    with pytest.raises(TemplateNotFound):
        template_store.read_or_plain("demo-dana-v2")


def test_render_branded_html_fills_every_slot_and_escapes_plain_text(
    branded_template_store: TemplateStore,
) -> None:
    template = branded_template_store.read()

    out = render_branded_html(
        template,
        title="A & B <Title>",
        article_html="<h1>Hello</h1><p>Body & content</p>",
        tokens_css="--primary: 25 62% 25%;",
        font_import_html='<link href="https://fonts.googleapis.com/x" rel="stylesheet">',
        logo_src="data:image/webp;base64,AAAA",
        source_revision="abc123<script>",
        rendered_at="2026-07-30T00:00:00+00:00",
    )

    # No leftover placeholders.
    assert "{{" not in out and "}}" not in out
    # Trusted markup blocks inserted verbatim.
    assert "<h1>Hello</h1><p>Body & content</p>" in out
    assert "--primary: 25 62% 25%;" in out
    assert '<link href="https://fonts.googleapis.com/x" rel="stylesheet">' in out
    assert 'src="data:image/webp;base64,AAAA"' in out
    # Plain-text fields are HTML-escaped (title/source_revision may carry untrusted characters).
    assert "A &amp; B &lt;Title&gt;" in out
    assert "abc123&lt;script&gt;" in out
    assert "demo-dana-v1" in out
    assert "2026-07-30T00:00:00+00:00" in out
    assert SYNTH_BRAND_MARKER in out


def test_plain_fallback_renders_the_article_unbranded(template_store: TemplateStore) -> None:
    """End-to-end shape of the degradation: real article, provenance footer, no brand markup."""
    template, _ = template_store.read_or_plain()

    out = render_branded_html(
        template,
        title="Plain piece",
        article_html="<h1>Hello</h1><p>Body</p>",
        tokens_css="",
        font_import_html="",
        logo_src="",
        source_revision="abc123",
        rendered_at="2026-07-30T00:00:00+00:00",
    )

    assert "{{" not in out and "}}" not in out
    assert "<h1>Hello</h1><p>Body</p>" in out
    assert "plain-v1" in out
    assert "abc123" in out
    assert SYNTH_BRAND_MARKER not in out
