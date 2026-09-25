# Review round-trip (open-decisions Item 7; domain model §1.14/§1.15)

Mint a Google Doc from a piece's frozen revision for one review round, collect the humans' comments
and inline edits, classify each, apply the machine-safe fixes, route everything else, and make the
round boundary explicit. Builds on the merged state machine, LLM provider, and data layer
(`ReviewRound` + `FeedbackItem` + the piece↔Doc link already live in `app/models/review_round.py` /
`app/models/feedback.py` and are already read back by the piece-detail screen).

## Pipeline

| Step | Module | What it does |
|------|--------|---------------|
| 1. Mint | `mint.py` | Freeze the current revision into a Doc — internal keeps the editorial block, external strips it (`app.render.editorial`, the same shared routine finalize uses) + adds the DRAFT banner + warns (never blocks) on open GAPs/clearances. Persists a new `ReviewRound` + the piece↔Doc link. |
| 2. Collect | `collect.py` | Every comment (`listComments`) + every diff-detected inline edit (the Doc's plain-text export vs. the frozen revision). Best-effort on the diff half only — a failed export still returns the comments. |
| 3. Preview | `preview.py` | Read-only "N comments · M edits — fold these in?" preview over the same collect logic, so preview and the real incorporate run can never disagree. |
| 4. Classify | `classify.py` | One batched Sonnet 5 call → `editorial-fix \| info-gap \| clearance \| out-of-scope` per item (instructed-JSON, same convention as `app.interview.classify`). |
| 5. Apply | `rewrite.py` | Opus 4.8 call folding only the `editorial-fix` items into the current revision ("edit the HTML, don't rebuild it") → the next Revision, committed to Git only on success. |
| 6. Route | `routing.py` | Every other item: info-gap → a targeted Interview record; clearance → the piece's owner; out-of-scope → a Vault Spike (`origin.kind=feedback`, mirrors the interview engine's tangent-parking). No silent drops — every item lands as a terminal-status `FeedbackItem`. |
| 7. Close + archive | `step.py` | `replyToComment` on every Doc-anchored item (best-effort), then the round flips to `archived` with its `routing_log` recorded. |

`IncorporateStep` (`step.py`) wires all of this behind the `BatchStep` seam
(`app/orchestration/steps.py`) as `JobType.incorporate`. The human "reviews done" trigger
(`PieceMachine.reviews_done`, already merged) dispatches it and — on success — auto-advances
`incorporating → council`, re-running the council on the new revision.

## Integration note (main.py wiring)

The REST surface (`routes.py`: mint + the assisted preview) is wired into `app/main.py` — it needs
no shared `StepRegistry` slot, so it carries no cross-ticket merge risk.

`IncorporateStep` **is** registered into `main.py`'s shared `StepRegistry`, alongside `OracleStep`,
unconditionally — never gated on `GOOGLE_OAUTH_CLIENT_ID`/`_SECRET`/`_REFRESH_TOKEN` at boot:

```python
registry.register(
    IncorporateStep(
        docs_client=HttpReviewDocsClient(
            settings.google_oauth_client_id,
            settings.google_oauth_client_secret,
            settings.google_oauth_refresh_token,
        )
    )
)
```

An earlier draft of this note proposed gating registration itself on credential presence (skip
`registry.register(...)` entirely when unconfigured). That was rejected: it would leave
`POST /api/pieces/{id}/reviews-done` returning 501 forever in an unconfigured deploy —
indistinguishable from "not implemented" even after this ticket landed. Instead this reuses the
same lazy-degrade idiom already used everywhere else in this stack: `HttpReviewDocsClient` (via
`HttpGoogleDocsClient._require_creds()`, `app/render/docs_export.py`) defers all credential
validation to call time, exactly like `IncorporateStep.run()` already treats `ctx.provider is
None` as a clean `PermanentStepError` rather than refusing to register. So in an unconfigured
deploy, `reviews-done` no longer 501s — it fails *inside* the dispatched job instead, with one of
(depending on how far it gets before hitting the gap): "no LLM provider configured" (no Anthropic
key), "no open review round for piece ... — mint a Doc before firing 'reviews done'" (no round was
ever minted, because `mint`/`preview` still 503 without Docs credentials — see `routes.py`'s
`_docs_client`), or "Google Docs export not configured" (a round exists but a live Docs call was
attempted). All three are `PermanentStepError`/non-retryable, surfaced on the piece's `failures`
list via the same `PieceStateResponse` a successful trigger returns — never a crash, never a
silent success. `test_orchestration.py`'s 501 contract still covers the *empty-registry* case
(no batch steps registered at all, e.g. Mongo-unconfigured tests); it was never specific to
incorporate.

**Registering a step whose success auto-chains into a still-unregistered step is safe.** Landing in
`incorporating` → success advances to `council`, which is not wired here either (a separate
downstream ticket). `PieceMachine._run_batch_chain` stops the chain in place when the next stage's
step isn't registered, the same way it stops at a genuine interactive stage — it does not enqueue a
job nothing can service. This guard used to be missing (see `content-machine-webapp` CLAUDE.md's
orchestration entry / `test_orchestration.py`'s
`test_chain_stops_cleanly_when_a_later_stage_step_is_unregistered`): registering *any* step whose
`_ON_SUCCESS` target lacked its own registered step used to raise `StepNotRegistered` out of
`JobRunner.run` **after** the prior job's success (and its Git/Mongo side effects) were already
committed — wedging the piece in the successor's stage with an orphaned `queued` job for it, while
the trigger's own HTTP response still read as a plain 501 that looked like nothing had happened.

## Admin provisioning

No new credential story: `HttpReviewDocsClient` extends `app.render.docs_export.HttpGoogleDocsClient`
and reuses the exact same server-side incremental-OAuth grant as the Drive connector / finalize's
clean-Doc export (`GOOGLE_OAUTH_CLIENT_ID` / `_CLIENT_SECRET` / `_REFRESH_TOKEN`,
`app/connectors/README.md`). It needs the same write-capable scope finalize's Doc export needs, plus
comment read/reply (`drive.file` already covers files it created; commenting on those files needs no
broader scope).

**(cmw-drive-named-folder-scoping)** `mint()` now parents each round's Doc inside the piece's Drive
folder (`app/drive/README.md`) when `GOOGLE_DRIVE_ROOT_FOLDER_NAME` is configured —
`ReviewMintService`'s
`share_file` call and everything else in this pipeline is unchanged; only the Doc's `parents` moves
from unset (Drive root) to the folder id. Unset, a round's Doc still lands loose at the root exactly
as before that ticket.
