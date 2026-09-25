"""Approval validity for AuthorizeRelease (cmw-release-semantics-impl).

An approval is tied to a specific Git revision (``Piece.approved_revision``, stamped when the
piece enters ``finalized`` or when ``accept-final-revision`` fires). AuthorizeRelease may only
mint a Publication Release against a *valid* approval:

- ``approved_revision == latest_revision`` → valid.
- They differ, but a ``TrivialEditWaiver`` covers that exact from→to pair → valid (the recorded
  waiver path for trivial final-pass edits).
- They differ and no waiver covers the pair → invalidated. AuthorizeRelease must refuse;
  council re-approval (or a new ``accept-final-revision``) is required.

Pure functions, no I/O — the workflow and the publish service both consult the same check.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models.publication import TrivialEditWaiver


@dataclass(frozen=True)
class ApprovalStatus:
    valid: bool
    invalidated: bool
    approved_revision: str | None
    current_revision: str | None
    waiver: TrivialEditWaiver | None
    reason: str

    @property
    def requirements(self) -> list[str]:
        if self.valid:
            return []
        if self.invalidated:
            return ["council-reapproval-or-trivial-edit-waiver"]
        return ["accepted-candidate"]


def approval_status(
    *,
    approved_revision: str | None,
    latest_revision: str | None,
    waivers: list[TrivialEditWaiver],
) -> ApprovalStatus:
    """Decide whether the current canonical revision is still the approved one."""
    if not approved_revision or not latest_revision:
        return ApprovalStatus(
            valid=False,
            invalidated=False,
            approved_revision=approved_revision,
            current_revision=latest_revision,
            waiver=None,
            reason="No quality-cleared revision has been accepted yet.",
        )
    if approved_revision == latest_revision:
        return ApprovalStatus(
            valid=True,
            invalidated=False,
            approved_revision=approved_revision,
            current_revision=latest_revision,
            waiver=None,
            reason="The accepted revision matches the current canonical content.",
        )
    matching = [
        waiver
        for waiver in waivers
        if waiver.from_revision == approved_revision and waiver.to_revision == latest_revision
    ]
    if matching:
        waiver = matching[-1]
        return ApprovalStatus(
            valid=True,
            invalidated=False,
            approved_revision=approved_revision,
            current_revision=latest_revision,
            waiver=waiver,
            reason="A recorded trivial-edit waiver covers the canonical change since approval.",
        )
    return ApprovalStatus(
        valid=False,
        invalidated=True,
        approved_revision=approved_revision,
        current_revision=latest_revision,
        waiver=None,
        reason=(
            "Canonical content changed since approval. Record a trivial-edit waiver, "
            "or accept the new revision after council re-approval."
        ),
    )
