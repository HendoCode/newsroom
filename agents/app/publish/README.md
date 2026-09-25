# Publish / AuthorizeRelease (finalized → released, HITL; immutable numbered Publication Releases)

A piece's original settled state machine ended at `finalized` — distribution was explicitly out of
scope for v1 (docs/design.md §9). Hendo reversed that: pieces need a way to be genuinely *done*,
with durable, public links to their outputs, not just a finished artifact stuck in an app-internal
stage forever. See `docs/design.md`'s D13 note and `agents/app/models/piece.py`'s
`ALLOWED_TRANSITIONS` comment for the settled reasoning (terminal, independent of the `lessons`
gate).

## What publish does

1. Reads the piece's `latest_revision` from Git (`GitContentStore.read_revision`) — refuses (400)
   if there isn't one yet.
2. Strips the editorial/GAP block (`app.render.editorial.strip_editorial_block` — the same D11/D13
   routine finalize and external review-share both use; never reimplemented) and extracts the
   semantic title/body (`app.render.semantic`).
3. Renders branded HTML from the versioned template + brand tokens
   (`app.render.brand`/`app.render.template` — the exact functions `FinalizeStep` uses), then a PDF
   from that same HTML via headless Chromium (best-effort: a missing/failing renderer warns and
   skips the PDF rather than failing the whole publish).
4. Uploads both to a plain, public-read S3 bucket (`app.publish.storage.S3PublishStorage`) under an
   **immutable, per-publish key** — `published/<slug>/<release>/branded.{html,pdf}`, where
   `release` is `Piece.published_release` incremented before minting the key. A re-publish (new
   render, new template version, whatever) only ever adds a new release; it never touches a prior
   one, so an already-circulating link keeps resolving. **S3 is unaffected by cmw-drive-piece-
   folders** — it stays the durable, public destination; the Drive folder is a parallel one, not a
   replacement.
5. (cmw-drive-piece-folders) Also uploads the same two files, unconverted, into the piece's Drive
   folder's `Published/` subfolder — never the finalize step's own originals living in the parent
   folder, moved or re-parented (the folder should honestly show both what was finalized and what
   actually shipped, which can differ). A no-op, and this step behaves exactly as it did before
   that ticket, unless `GOOGLE_DRIVE_ROOT_FOLDER_NAME` is configured — see `app/drive/README.md`.
6. Mints a fresh Google Doc snapshot of the same content — inside that same `Published/` subfolder
   when one exists, otherwise at the Drive root exactly as before cmw-drive-piece-folders — and
   shares it anyone-with-the-link/reader (`share_file`, the same call `ReviewMintService`'s
   `ShareMode.external` path uses — but NOT that service itself, which always creates a
   `ReviewRound`; this must never create one). Deliberately skips that path's "DRAFT — not for
   external distribution" banner: it would be false here. The two Drive HTML/PDF uploads from step
   5 get the same `share_file` reader/anyone grant, for parity with the S3 objects' public nature.
7. Only once every step above has succeeded does it persist the links on the `Piece` and flip
   `finalized → published` via `PieceMachine.publish` — no partial state on a failure.

## Why NOT the finalize step's own render output

`FinalizeStep` already renders branded HTML/PDF, but that render is documented (§1.19) as
disposable/regenerable and is written straight to the git-ignored working tree
(`drafts/<slug>/finalized/`) — instance-local, not a store-of-record. In a multi-instance or
since-redeployed setup it may not exist on whichever container handles a `publish` request. This
service performs its own fresh render from the same seams instead of trusting that file.

## Bucket / access model (deliberately simple, iterable later)

No signed URLs, no unguessable keys, no access-control layer — Hendo's explicit v1 call. The bucket
is generally public by policy (bucket listing off, so it's not a browsable index, but any object's
plain key resolves for anyone). Tightening this later (signed URLs, a CDN, per-object ACLs) is
cheap; it just can't un-share a URL already circulating. See `infra/aws-poc/publish_bucket.tf`.

## Configuration

`PUBLISHED_ASSETS_BUCKET` / `PUBLISHED_ASSETS_REGION` (`app/config.py`, plain — not secrets, just
resource identifiers) name the bucket `S3PublishStorage` uploads to. Blank bucket → the route 503s
rather than failing boot (same degrade-gracefully discipline as every other optional subsystem
here). Google Docs sharing reuses the same `GOOGLE_OAUTH_CLIENT_ID`/`_SECRET`/`_REFRESH_TOKEN` grant
as finalize/review. `GOOGLE_DRIVE_ROOT_FOLDER_NAME` (cmw-drive-named-folder-scoping, `app/drive/README.md`) gates
the `Published/` Drive uploads above — blank, this route's S3/Doc behavior is completely unaffected
(no 503, since the Drive half was always optional-in-parallel, never a requirement to publish).

## Integration note (main.py wiring)

`routes.py` is wired into `app/main.py` directly (`app.include_router(publish_router)`) — it needs
no `StepRegistry` slot (publish is a synchronous HITL action composing a service, like the review
round's mint, not a batch `JobType`). The route path is `POST /api/pieces/{piece_id}/publish`,
matching the generic `/api/pieces/{piece_id}/{trigger}` shape the orchestration triggers use —
`web/`'s BFF trigger proxy forwards to that shape already, so `"publish"` only needed adding to its
allow-list (`web/lib/agents-client.ts`'s `PieceTrigger`, `app/api/pieces/[pieceId]/trigger/
route.ts`'s `ALLOWED_TRIGGERS`), no new BFF route.
