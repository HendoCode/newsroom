"""Finalize render: branded HTML + PDF + clean Google Doc from the semantic draft (D13, Item 5).

Runs in the ``finalizing`` stage of the settled 9-state machine (domain model §1.9) as a
:class:`~app.orchestration.steps.BatchStep` — a pure render, no LLM call. See :mod:`app.render.step`
for the pipeline; the other modules here are its seams (editorial strip, semantic extraction, brand
tokens, the versioned template, PDF/Docs export), each independently testable and each reusable by
future tickets (the editorial strip in particular, per the domain model, is meant to be shared with
a D11 external-share implementation).

Integration note: this package registers no route and is not wired into ``app/main.py``. Batch
steps are registered into a shared :class:`~app.orchestration.steps.StepRegistry`; wiring every real
step (oracle/draft/council/incorporate/finalize) into that registry happens once, together, when
all the sibling pipeline-step tickets have landed — see the module docstring in
``app/orchestration/steps.py``. :func:`build_finalize_step` is that integration point for this step.
"""

from __future__ import annotations

from app.render.brand import (
    BrandTokenError,
    BrandTokens,
    LogoFetchError,
    derive_brand_tokens,
    fetch_logo_data_uri,
)
from app.render.docs_export import DocRef, DocsExportError, GoogleDocsClient, HttpGoogleDocsClient
from app.render.editorial import has_editorial_block, strip_editorial_block
from app.render.pdf import ChromiumPdfRenderer, PdfRenderer, PdfRenderError
from app.render.semantic import extract_semantic_body, extract_title
from app.render.step import ALL_FORMATS, FinalizeOutputs, FinalizeStep
from app.render.template import (
    TEAM_VOICE_TEMPLATE_VERSION,
    BrandedTemplate,
    TemplateNotFound,
    TemplateStore,
    render_branded_html,
)

__all__ = [
    "ALL_FORMATS",
    "TEAM_VOICE_TEMPLATE_VERSION",
    "BrandTokenError",
    "BrandTokens",
    "BrandedTemplate",
    "ChromiumPdfRenderer",
    "DocRef",
    "DocsExportError",
    "FinalizeOutputs",
    "FinalizeStep",
    "GoogleDocsClient",
    "HttpGoogleDocsClient",
    "LogoFetchError",
    "PdfRenderError",
    "PdfRenderer",
    "TemplateNotFound",
    "TemplateStore",
    "build_finalize_step",
    "derive_brand_tokens",
    "extract_semantic_body",
    "extract_title",
    "fetch_logo_data_uri",
    "has_editorial_block",
    "render_branded_html",
    "strip_editorial_block",
]


def build_finalize_step(settings: object | None = None) -> FinalizeStep:
    """Construct a production :class:`FinalizeStep` from service settings.

    The integration point a follow-up wiring pass (once all batch steps exist) registers into
    ``app.state.step_registry`` in ``app/main.py``, alongside oracle/draft/council/incorporate.
    """
    from app.config import get_settings
    from app.drive import HttpDriveFolderClient

    resolved = settings or get_settings()
    template_store = TemplateStore(resolved.brain_root)
    pdf_renderer = ChromiumPdfRenderer()
    # One client covers both roles (create-Doc and folder/upload) — `HttpDriveFolderClient`
    # extends `HttpGoogleDocsClient`, so it satisfies both constructor params without a second,
    # redundant OAuth-credentialed object (cmw-drive-piece-folders).
    docs_client = HttpDriveFolderClient(
        resolved.google_oauth_client_id,
        resolved.google_oauth_client_secret,
        resolved.google_oauth_refresh_token,
    )
    return FinalizeStep(
        template_store=template_store,
        pdf_renderer=pdf_renderer,
        docs_client=docs_client,
        drive_client=docs_client,
        root_folder_name=resolved.google_drive_root_folder_name,
    )
