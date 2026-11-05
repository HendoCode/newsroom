"""Synthetic brand assets for the branded-render tests (D13, Item 5).

The brain repo (`HendoCode/masthead`) is the **neutral demo suite**: it deliberately carries no
personal branding — no `voice/demo-dana/visual-identity.md`, no `brand-guidelines.md`, no
`templates/branded/*.html`. Production therefore renders plain/unbranded output against it (the
graceful degradation in `app/render/template.py` + `app/render/brand.py`).

The branded path still needs coverage, so this module holds a small **test-only** stand-in for
those three files and seeds them into the throwaway copy of the brain that `tests/conftest.py`
builds per test. Nothing here ever lands in the brain fixture
(`agents/tests/fixtures/brain/` stays a pure snapshot of `agents/brain.lock`'s pinned ref — see
`tests/test_brain_fixture.py`), and every value is obviously synthetic: the fonts, colors and logo
host are invented, so a real brand can never be mistaken for this fixture.

Structural convention matters more than content here: `app/render/brand.derive_brand_tokens` parses
the fenced blocks below by regex, exactly as it does the real `visual-identity.md`.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

# The one template version v1 ships (app/render/template.TEAM_VOICE_TEMPLATE_VERSION).
SYNTH_BRANDED_TEMPLATE_REL = "templates/branded/demo-dana-v1.html"
SYNTH_VISUAL_IDENTITY_REL = "voice/demo-dana/visual-identity.md"
SYNTH_BRAND_GUIDELINES_REL = "voice/demo-dana/brand-guidelines.md"

# A distinctive marker so a test can prove the *branded* template rendered, not the plain fallback.
SYNTH_BRAND_MARKER = "SYNTHETIC-BRANDED-TEMPLATE"
# Deliberately an unroutable loopback port: the branded tests assert the logo warns-and-carries-on
# (app/render/brand.fetch_logo_data_uri) with an instant connection refusal, never a real fetch.
SYNTH_LOGO_URL = "http://127.0.0.1:1/synthetic-logo.svg"

SYNTH_VISUAL_IDENTITY_MD = f"""# Synthetic Visual Identity (test fixture — NOT the real brand)

> Test-only stand-in for a voice pack's visual identity. Everything below is invented; it exists so
> `app/render/brand.py`'s derivation has the fenced blocks its regexes expect.

## 2. Color Palette

```css
:root {{
  --background:  44 35% 94%;   /* synthetic cream */
  --card:        45 36% 96%;
  --foreground:  209 39% 19%;  /* synthetic slate */
  --muted-foreground: 207 32% 43%;
  --primary:     206 35% 28%;
  --border:      45 20% 83%;
  --radius:      0.75rem;
}}
```

## 3. Typography

```css
--font-serif: 'Synth Serif', Georgia, serif;
--font-sans: 'Synth Sans', system-ui, sans-serif;
--font-mono: 'Synth Mono', ui-monospace, monospace;
```

```html
<link href="https://fonts.googleapis.com/css2?family=Synth+Sans&display=swap" rel="stylesheet">
```

## 6. Logo

**Full logo:** `{SYNTH_LOGO_URL}`
"""

SYNTH_BRAND_GUIDELINES_MD = """# Synthetic Brand Guidelines (test fixture — NOT the real brand)

Test-only copy of the voice pack's brand guidelines: naming, capitalization and the one rule the
tests assert on — never invent credentials.
"""

SYNTH_BRANDED_TEMPLATE_HTML = f"""<!DOCTYPE html>
<!-- {SYNTH_BRAND_MARKER} — synthetic stand-in for the brain's branded distribution template. -->
<html lang="en">
<head>
<meta charset="utf-8">
<title>{{{{TITLE}}}}</title>
{{{{FONT_IMPORT}}}}
<style>
  :root {{
{{{{TOKENS_CSS}}}}
  }}
  body {{ font: 15px/1.7 var(--font-sans, system-ui, sans-serif); margin: 0; }}
  .branded-page {{ max-width: 760px; margin: 0 auto; padding: 0 1.5rem 4rem; }}
  .branded-header img {{ height: 28px; width: auto; }}
  .branded-footer {{ font-size: 0.78rem; color: #555; margin-top: 3rem; }}
</style>
</head>
<body>
<div class="branded-page">
  <header class="branded-header">
    <img src="{{{{LOGO_SRC}}}}" alt="Synthetic" />
  </header>
  <main>
{{{{ARTICLE_HTML}}}}
  </main>
  <footer class="branded-footer">
    <p>Rendered {{{{RENDERED_AT}}}} &middot; source revision {{{{SOURCE_REVISION}}}} &middot; template {{{{TEMPLATE_VERSION}}}}</p>
  </footer>
</div>
</body>
</html>
"""


def seed_synth_brand(root: Path) -> Path:
    """Write the synthetic brand files into the temp brain repo ``root`` and commit them, so the
    template read gets a real Git sha like it does against a brain that ships branding."""
    for rel, content in (
        (SYNTH_BRANDED_TEMPLATE_REL, SYNTH_BRANDED_TEMPLATE_HTML),
        (SYNTH_VISUAL_IDENTITY_REL, SYNTH_VISUAL_IDENTITY_MD),
        (SYNTH_BRAND_GUIDELINES_REL, SYNTH_BRAND_GUIDELINES_MD),
    ):
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.email=t@test",
            "-c",
            "user.name=test",
            "commit",
            "-q",
            "-m",
            "seed synthetic brand assets",
        ],
        check=True,
    )
    return root
