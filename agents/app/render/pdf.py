"""The PDF-render seam: headless Chromium over the exact branded HTML (D13, Item 5).

Item 5's explicit requirement: "PDF = render that branded HTML to PDF via headless Chromium (a
print pass over the exact branded HTML), so HTML and PDF are guaranteed to match." There is
deliberately no separate PDF template — the renderer only ever sees the same
``render_branded_html`` output the HTML format uses (Item 5 rejected alternative: "generate PDF
independently of the branded HTML").

``playwright`` (Chromium bindings) is an optional runtime dependency: the import is guarded so a
service/test environment without the package (or its downloaded browser binary — a separate
``playwright install chromium`` provisioning step, akin to the Slack-app/Drive-OAuth admin actions
noted in open-decisions Item 6) still boots; only a PDF request degrades with one clear error type,
never a bare ``ImportError`` leaking out of the step.
"""

from __future__ import annotations

from typing import Protocol


class PdfRenderError(RuntimeError):
    """Chromium isn't available, or the print-to-PDF pass failed."""


class PdfRenderer(Protocol):
    """Render a self-contained HTML string to PDF bytes. Tests inject a fake; production wires
    :class:`ChromiumPdfRenderer`."""

    async def render(self, html: str) -> bytes: ...


class ChromiumPdfRenderer:
    """Real :class:`PdfRenderer` via Playwright's headless Chromium (fonts embedded by the browser
    from the ``<link>``/base64 logo already in the HTML — no separate embedding step needed)."""

    def __init__(self, *, timeout_ms: float = 30_000) -> None:
        self.timeout_ms = timeout_ms

    async def render(self, html: str) -> bytes:
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise PdfRenderError(
                "playwright is not installed (or `playwright install chromium` has not been run) "
                "— HTML/Doc formats are unaffected; provision Chromium to enable PDF"
            ) from exc
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch()
                try:
                    page = await browser.new_page()
                    await page.set_content(html, wait_until="networkidle", timeout=self.timeout_ms)
                    return await page.pdf(print_background=True, prefer_css_page_size=True)
                finally:
                    await browser.close()
        except PdfRenderError:
            raise
        except Exception as exc:
            raise PdfRenderError(f"Chromium PDF render failed: {exc}") from exc
