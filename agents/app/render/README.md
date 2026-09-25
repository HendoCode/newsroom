# Finalize render (D13, open-decisions Item 5)

Turns a piece's current semantic `draft.html` revision into the branded distribution outputs at
finalize: **branded HTML**, a **matching PDF** (rendered from that same HTML via headless
Chromium), and a **clean Google Doc**. A pure render — **no LLM call**. Runs in the `finalizing`
stage of the settled 9-state machine (domain model §1.9); `app.orchestration.machine.PieceMachine`
owns advancing `finalizing → finalized` on success.

Content stays plain/semantic and is the master; the branded render is **disposable** — regenerable
from the draft + the versioned template, never a system of record (§1.19).

## Pipeline

| Step | Module | What it does |
|------|--------|---------------|
| 1. Read | `app.git.content.GitContentStore` | The current `draft.html` (the semantic master). |
| 2. Strip | `editorial.py` | Remove the trailing `<section class="editorial">` block — the **same shared routine** a future D11 external-share ticket reuses. |
| 3. Extract | `semantic.py` | Title + injectable body (`<article>` if present, else the whole `<body>`) — stdlib `re` only. |
| 4. Derive tokens | `brand.py` | Parse the `:root` CSS tokens, font variables/import, and logo URL out of `demo-dana/visual-identity.md` — **derived, never duplicated** (Item 5). |
| 5. Inject | `template.py` | Fill the versioned template's `{{SLOT}}`s (the brain's `templates/branded/demo-dana-v1.html`, read with its Git commit sha for reproducibility). |
| 6. Render | `pdf.py` / `docs_export.py` | PDF via headless Chromium over the exact branded HTML; a clean Doc (semantic content only, styling stripped) via the Drive create-with-conversion trick. |
| 7. Record | `step.py` | Source revision + template version on every output (a visible footer on HTML/PDF, the Drive file `description` on the Doc); the Doc link on `Piece.final_doc`. |

`FinalizeStep` (`step.py`) wires all of this behind the `BatchStep` seam
(`app/orchestration/steps.py`). `formats` are selectable (use case J): pass a subset via
`Job.formats` (default is all of `html`/`pdf`/`doc`). A renderer that's missing or fails for one
requested format **warns and skips it** rather than failing the whole job — mirrors Item 4's "one
editor's failure completes-with-gap"; only zero-of-requested-formats is a real failure.

Outputs are written to the piece's `drafts/<slug>/finalized/` folder (branded.html /branded.pdf /
google-doc.json) — **git-ignored**, never committed, since the render is disposable (§1.19). This
local copy is instance-local and was, until cmw-drive-piece-folders, the *only* copy — genuinely
unreachable outside the container. That ticket also uploads real, unconverted `branded.html`/
`branded.pdf` copies (and parents the clean Doc) into the piece's named My-Drive-root folder, gated behind
`GOOGLE_DRIVE_ROOT_FOLDER_NAME` — see `app/drive/README.md` for the folder design (the app
finds-or-creates the named root itself under the `drive.file` scope, no Shared-Drive
provisioning needed). Unset, this step's
behavior is byte-for-byte what it was before that ticket.

## Integration note (main.py wiring)

This package registers no route and is not wired into `app/main.py`. Batch steps register into a
shared `StepRegistry`; wiring every real step (oracle/draft/council/incorporate/finalize) happens
once, together, when the sibling pipeline-step tickets have all landed — avoids N-way merge
conflicts on `main.py` from parallel tickets. `build_finalize_step()` (`app/render/__init__.py`) is
the integration point: it builds a production `FinalizeStep` from `Settings` and is ready to
`registry.register(build_finalize_step())` alongside the other steps.

## Admin provisioning

Both external renderers are **optional at boot** — a missing one degrades only the format it
serves (never crashes the service, per the guarded-import / warn-and-skip design above).

### PDF — headless Chromium via Playwright

`playwright` is pinned in `requirements.txt`; the browser binary is a separate one-time step:

```
playwright install chromium
```

Without it, `ChromiumPdfRenderer.render()` raises a clear `PdfRenderError` (never a bare
`ImportError`) and PDF requests are skipped with a warning; HTML/Doc are unaffected.

### Clean Google Doc — reuses the Drive connector's OAuth grant

No new credential story: `HttpGoogleDocsClient` authorizes over the **same** server-side
incremental-OAuth grant the Google Drive connector uses (`app/connectors/README.md`) —
`GOOGLE_OAUTH_CLIENT_ID` / `_CLIENT_SECRET` / `_REFRESH_TOKEN`. It needs write access (the Drive
`drive.file` scope covers files it creates) in addition to the Drive connector's `drive.readonly`
scope — `app/connectors/README.md`'s provisioning steps request **both** scopes in the one-time
consent up front for exactly this reason, so there's no separate grant to provision here. If an
older client was provisioned read-only-only, re-run that consent with both scopes added rather
than treating this as a second credential.
