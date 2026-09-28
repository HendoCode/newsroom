# Per-piece Google Drive folders under one named My-Drive root (cmw-drive-named-folder-scoping)

Every Google artifact a piece produces — each review-round Doc (`app.review.mint`), the finalized
clean Doc + branded HTML/PDF (`app.render.step`), and publish's own re-rendered copies
(`app.publish.service`) — lands in **one folder per piece**, parented under a single specifically-
named folder in the app account's own My Drive, instead of loose at the Drive root. See
`folder.py`'s module docstring for the design (idempotent-by-pointer for piece folders, by-name
for the root) and `http_client.py` for the real Drive v3 mechanics.

## What's here

| Module | What it does |
|--------|---------------|
| `folder.py` | `DriveFolderClient` (the seam), `PieceDriveFolders` (resolves the named root once per process, then ensures/reuses the piece folder + its `Published/` subfolder under it, persisting the pointer on `Piece`), framework-free and independently unit-tested (`agents/tests/test_drive_folder.py`). |
| `http_client.py` | `HttpDriveFolderClient` — the real implementation, extending `app.render.docs_export.HttpGoogleDocsClient` to reuse its OAuth token dance. Adds `find_or_create_folder` (a `files.list` name-match under My Drive, else `create_folder`), `create_folder`/`upload_file` (both kept `supportsAllDrives=true` — harmless no-ops for a personal My Drive, needed if a target ever parents into a Shared Drive again). Request-shape tests: `agents/tests/test_drive_http_client.py`. |

`app.render.docs_export.HttpGoogleDocsClient.create_doc_from_html` itself gained an optional
`parent_id` (used by finalize/review/publish to put a Doc inside the piece's folder) — see that
module, not this one, since every Doc-creating caller (finalize, review mint, publish) already
went through it before the folder work existed.

## Folder layout

```
<My Drive>/
  <GOOGLE_DRIVE_ROOT_FOLDER_NAME>/   # the named root the app finds-or-creates itself (e.g. "newsroom")
    <piece-slug>/                    # one per piece, named after its Git slug (drafts/<slug>/...)
      <review round Docs>            # each round's mint, in creation order
      <finalized Doc>                # the current clean Doc (re-created, not versioned, per finalize run)
      branded.html                   # ordinary text/html upload — NEVER converted to a Google Doc
      branded.pdf                    # ordinary application/pdf upload
      Published/                     # only once the piece has been published at least once
        <published Doc>
        branded.html                 # publish's own fresh re-render — NEVER the finalize files above,
        branded.pdf                  #   moved or re-parented (Hendo's call: the folder should show
                                      #   both what was finalized and what actually shipped)
```

Folder naming and "adopt pre-existing loose Docs?" were open calls the original ticket settled (see
its PR description for the full reasoning): the folder is named after the piece's Git slug (the same
identity already used for `drafts/<slug>/...` paths), and pre-existing loose Docs from before folder
scoping are **never** retroactively adopted into a folder — only new artifacts, from the first
finalize/mint/publish after `GOOGLE_DRIVE_ROOT_FOLDER_NAME` is configured, land in one.

## Configuration — nothing to provision (the app creates the root itself)

**No Shared Drive, no Content-Manager membership, no out-of-band setup.** The app's own Google
account (behind `GOOGLE_OAUTH_CLIENT_ID`/`_SECRET`/`_REFRESH_TOKEN`) finds-or-creates the named root
folder in its own My Drive under the `drive.file` scope — which already confines the whole grant to
files this app itself created, so scoping to "one folder this app made" is naturally the tightest
`drive.file`-compatible arrangement.

1. Pick a folder name (e.g. `newsroom`) and set it as `GOOGLE_DRIVE_ROOT_FOLDER_NAME` — a
   plain folder **name**, **not a secret**, following the exact same settings pattern as
   `PUBLISHED_ASSETS_BUCKET` (`app/config.py`, `app/publish/README.md`). Env key the agents service
   reads: `GOOGLE_DRIVE_ROOT_FOLDER_NAME` (docker-compose/.env wiring is in the root
   `docker-compose.yml` + `.env.example` and `agents/.env.example`).
2. Leave it blank for local dev / any environment that doesn't need this yet: every caller
   (`PieceDriveFolders.enabled`) then behaves exactly as it did before folder scoping — Docs land
   loose at the Drive root, no HTML/PDF Drive upload, no folder pointers ever written onto a
   `Piece`. Nothing crashes; this degrades the same way an unset `PUBLISHED_ASSETS_BUCKET` does.
3. **The root must be app-created via the find-or-create path, never a human-provisioned id.** Under
   the `drive.file` scope the app only sees files it created, so a folder a human pre-creates by
   hand would be invisible to it — do not resolve a pre-created folder's id and feed it in; let the
   app create the named root on first use.

**No new OAuth scope.** Folder search (`files.list`), creation (`files.create` with `mimeType:
application/vnd.google-apps.folder`), and ordinary file upload are the same Drive v3 endpoints and
the same credential as the Doc creation this OAuth grant already authorizes — confirmed against the
live Drive API reference during the original folder ticket (`drive.file` is one of the documented
accepted scopes for `files.create`), not assumed. If a future scope requirement is ever discovered,
that is loud enough to need re-consent + a re-minted refresh token — see that PR's description for
how it was verified.

## What a future unshare (cmw-unpublish-piece) needs to know

Unpublish is expected to unshare the piece's Drive folder, resiliently. The folder work deliberately
left that implementation for later, but shaped the state it depends on:

- `Piece.drive_folder_id` / `drive_published_folder_id` are the only persisted pointers — an
  unshare should operate on these ids directly (e.g. `permissions.list` + delete, or simply
  removing whatever explicit grants were ever added — this module never grants folder-level
  access itself, see below) rather than re-deriving them.
- **Nothing here shares the piece folder itself** — visibility comes from the relevant lockers'
  existing access to the app account's Drive (the root folder is in the app's own My Drive) for
  internal reviewers, and from the existing per-file `share_file` grants (review Docs, the
  published Doc, and now the published Drive HTML/PDF) for anyone else. An unshare therefore has
  two independent things to potentially undo: folder membership (the root being in the app's own
  My Drive — out of this code's control, same as granting it) and per-file permissions
  (`permissions.list`/`permissions.delete` on each recorded file id).
- **Must tolerate missing objects.** A human may have already deleted a file/folder by hand before
  unpublish runs — any Drive call here 404s cleanly (`DriveFolderError`/an `httpx` 4xx), never
  raises an uncaught exception; a future unshare should catch and continue rather than assume every
  recorded id still resolves.
- **Idempotent by construction, not by extra state.** Re-running `ensure_piece_folder`/
  `ensure_published_subfolder` never creates a second folder as long as the Piece pointer survives
  — an unshare implementation gets to assume "this id, if set, is the one real folder" for free.