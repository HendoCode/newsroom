"""The versioned branded template: read + slot injection (D13, Item 5; domain model §1.19).

Item 5 settled that the template lives in the **same Git store** as the brain/content — "Git gives
the versioned property for free, consistent with D2" — rather than a second, inferior versioning
scheme in Mongo. So this module opens the same repo :mod:`app.git` already discovers (via
``brain_root``) and reads the one template file v1 ships:
``templates/branded/demo-dana-v1.html``.

Reproducibility (Item 5: "the finalized artifact records which template version rendered it, so a
re-render is reproducible") comes from two things recorded together: the stable ``version`` label
(``demo-dana-v1`` — bump this only when a deliberately-new template variant ships) and the Git
commit ``sha`` that last touched the file (so even an in-place edit under the same version is
traceable to an exact commit).

Injection is plain ``{{SLOT}}`` substitution — no templating-engine dependency for one template
with a handful of slots (Item 5: "the template is then a thin render layer").
"""

from __future__ import annotations

import html as _html
from dataclasses import dataclass

from app.git.repo import GitRepo, discover_repo

# v1 ships exactly one demo-dana template (Item 5 scope boundary) — bump this label (and add a
# new file) only for a deliberately new template variant, never for an in-place tweak.
TEAM_VOICE_TEMPLATE_VERSION = "demo-dana-v1"
_TEMPLATE_REL_PATH = "templates/branded/demo-dana-v1.html"


class TemplateNotFound(RuntimeError):
    """The versioned template file is missing from the Git store."""


@dataclass(frozen=True)
class BrandedTemplate:
    version: str  # the stable version label recorded on every render (Item 5 reproducibility)
    path: str  # git-relative path, for provenance
    html: str  # the raw `{{SLOT}}`-templated skeleton
    sha: str | None  # commit sha that last touched the file (None only if the repo has no history)


class TemplateStore:
    """Reads the versioned branded template out of the same Git repo as the brain (D1/D2)."""

    def __init__(self, brain_root: str, *, repo: GitRepo | None = None, prefix: str = "") -> None:
        if repo is None:
            repo, prefix = discover_repo(brain_root)
        self.repo = repo
        self.prefix = prefix

    def _p(self, rel: str) -> str:
        return f"{self.prefix}/{rel}" if self.prefix else rel

    def read(self, version: str = TEAM_VOICE_TEMPLATE_VERSION) -> BrandedTemplate:
        """Read the named template version. v1 has exactly one; an unknown version is a bug, not a
        soft-fail — better to raise loudly than silently render with the wrong brand."""
        if version != TEAM_VOICE_TEMPLATE_VERSION:
            raise TemplateNotFound(
                f"unknown template version {version!r} (v1 ships only {TEAM_VOICE_TEMPLATE_VERSION!r})"
            )
        rel = self._p(_TEMPLATE_REL_PATH)
        if not self.repo.exists(rel):
            raise TemplateNotFound(f"branded template not found at {rel!r}")
        html = self.repo.read_text(rel)
        history = self.repo.log(rel, max_count=1)
        sha = history[0].sha if history else None
        return BrandedTemplate(version=version, path=rel, html=html, sha=sha)


def render_branded_html(
    template: BrandedTemplate,
    *,
    title: str,
    article_html: str,
    tokens_css: str,
    font_import_html: str,
    logo_src: str,
    source_revision: str,
    rendered_at: str,
) -> str:
    """Fill the template's ``{{SLOT}}`` placeholders with derived tokens + the stripped semantic
    content. ``article_html``/``font_import_html``/``logo_src``/``tokens_css`` are trusted, already
    render-ready markup and are inserted verbatim; the plain-text fields are HTML-escaped."""
    slots = {
        "TITLE": _html.escape(title),
        "ARTICLE_HTML": article_html,
        "TOKENS_CSS": tokens_css,
        "FONT_IMPORT": font_import_html,
        "LOGO_SRC": logo_src,
        "SOURCE_REVISION": _html.escape(source_revision),
        "TEMPLATE_VERSION": _html.escape(template.version),
        "RENDERED_AT": _html.escape(rendered_at),
    }
    out = template.html
    for key, value in slots.items():
        out = out.replace("{{" + key + "}}", value)
    return out
