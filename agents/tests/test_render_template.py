"""Versioned branded template: read (with Git provenance) + slot injection (D13, Item 5).

``brain_repo`` (conftest.py) is a temp git repo seeded with a copy of the real brain, which now
includes ``templates/branded/demo-dana-v1.html`` — so this proves the template is genuinely
versioned in the same store as everything else, with a real commit sha.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.render.template import (
    TEAM_VOICE_TEMPLATE_VERSION,
    TemplateNotFound,
    TemplateStore,
    render_branded_html,
)


@pytest.fixture
def template_store(brain_repo: Path) -> TemplateStore:
    return TemplateStore(str(brain_repo))


def test_reads_the_real_versioned_template(template_store: TemplateStore) -> None:
    template = template_store.read()

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


def test_render_branded_html_fills_every_slot_and_escapes_plain_text(
    template_store: TemplateStore,
) -> None:
    template = template_store.read()

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
