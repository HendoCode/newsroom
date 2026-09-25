# Release semantics (Released + immutable Publication Releases + AuthorizeRelease)

Captain-approved 2026-08-31 (domain-model release-semantics + state-audit release-doctrine +
state-audit final-pass-invalidation). Replaces the conflicting terminal-`published` + republish
comments that could not actually re-publish (the stage was terminal; the service required
`finalized`).

## Doctrine

1. **`released` is the terminal Piece stage.** A piece that has been authorized at least once
   sits in `released`. There is no edge back out — a circulating public link cannot be un-shared,
   so the stage must not imply the action is reversible. Legacy documents stored as `published`
   coerce to `released` on read (`PieceStage._missing_`).
2. **What shipped is a Publication Release, not the stage.** Releases are numbered (1, 2, …),
   insert-only, and never overwritten. Authorizing again from `released` appends N+1; it does
   not change stage and does not mutate release N. The `Piece.published_*` fields remain a
   convenience pointer at the *latest* release for existing UI.
3. **The machine never publishes.** The only writer of a Publication Release is an explicit
   human **AuthorizeRelease** — the content-workflow `authorize-release` command, or the
   piece-detail HITL button (`POST /api/pieces/{id}/publish`) that runs the same
   `PublishService`. Finalize, council, and draft never mint a release.
4. **The workspace is not terminal after release.** Authorizing a release does **not** flip
   `ContentProject.disposition` to `completed`. The project stays active (derivatives, another
   release, lessons). `ProjectPhase.completed` is only for an explicit abandonment/completion.
5. **Final-pass invalidation.** An approval is tied to a Git revision (`Piece.approved_revision`,
   stamped when the piece enters `finalized` or when `accept-final-revision` fires). If
   `latest_revision` then changes:
   - **substantive** (default): approval is invalidated; AuthorizeRelease refuses until the new
     revision is re-accepted (`accept-final-revision` — the council-reapproval path).
   - **trivial**: an explicit recorded `TrivialEditWaiver` (actor + reason, never silent) covers
     that from→to pair and keeps the approval valid.

## Authority seam (for the queued authority-model task)

AuthorizeRelease records `authorized_by` on every Publication Release and consults
`AuthorityKind.release` when *projecting* the command (`inspect()` already attaches
`authority_required=release` + `assigned_actor`). It does **not** yet enforce that the submitting
actor holds that assignment — attribution-only, matching every other command here (§1.17).

The queued per-project authority-model task should wrap **one** check, in one place:

- `ContentWorkflow._authorize_release` (the command path)
- `PublishService.publish` (the piece-detail HITL path)

both already funnel through `app.release.approval.approval_status` for the revision gate. Add
the actor-vs-assignment check next to that call (or as a sibling `_require_release_authority`
consulted by both) rather than inside the UI or the stage machine. Do not silently treat
AuthorizeRelease as machine-fireable while adding that check.

## Surfaces

- Command: `authorize-release`, `accept-final-revision`, `record-trivial-edit-waiver`
  (`app/content_workflow`).
- HITL mint: `POST /api/pieces/{id}/publish` (same as before; now legal from `released` too,
  and refuses when approval is invalidated).
- Waiver (legacy piece, no ContentProject): `POST /api/pieces/{id}/waivers/trivial-edit`.
- List: `GET /api/pieces/{id}/releases`.
- Projection: `ProjectWorkspaceView.release` (`ReleaseGateView`).
