"""Derivative quality bar: destination-specific councils + universal hard gates.

Every publishable native derivative must clear **its own council** at :data:`DERIVATIVE_QUALITY_BAR`
(9/10) — an anchor's score never certifies its natives. Judgment is **destination-specific**: a
LinkedIn post and a whitepaper need different editors (the registry here maps each destination to
the editor personas whose judgment criteria fit that native), while two **universal hard gates**
apply to every destination regardless of its lineup:

* ``facts`` — enforced by ``technical-reviewer``'s hard cap: a factual error caps the aggregate
  below the bar no matter what the other editors score;
* ``safety`` — enforced by ``slop-allergist``'s hard cap (slop/safety tells) PLUS the same
  open-clearance hard block :mod:`app.review.mint` applies to external sharing.

The publish-time enforcement half lives in :mod:`app.publish.service` (``derivative_publish_gate``
is called before any external side effect); the council-lineup half is consumed by
:meth:`app.orchestration.council_step.CouncilStep._select_editors` for pieces with
``role=derivative``.

Keep the destination→editors registry below in sync with ``web/lib/pieces/derivatives.ts``'s
``DESTINATION_COUNCIL_EDITORS`` (same canonical ids, same aliases via ``DERIVATIVE_FORMATS``) —
there is no shared schema; the web mirror is display-only, this module is the enforcement side.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.models import Council, Piece, PieceRole
from app.models.council import MANDATORY_EDITORS
from app.repositories import WorkStateStore

# The bar every publishable derivative clears on ITS OWN council (never inherited from the anchor).
DERIVATIVE_QUALITY_BAR = 9.0

# Canonical order for the mandatory editors (mirrors council_step._MANDATORY_ORDER).
_MANDATORY_ORDER: tuple[str, ...] = ("slop-allergist", "voice-guardian")

# Universal hard gates: gate name -> the editor whose hard-cap authority enforces it. These
# editors run on EVERY derivative council regardless of destination. (The safety gate also gets
# the open-clearance hard block at publish time — see derivative_publish_gate below.)
UNIVERSAL_HARD_GATES: dict[str, str] = {
    "facts": "technical-reviewer",
    "safety": "slop-allergist",
}
UNIVERSAL_GATE_NAMES: tuple[str, ...] = ("facts", "safety")

# Destination-specific judgment: canonical format id -> the editor personas whose judgment
# criteria fit that native (see the fixture/brain editors' own rubrics). Deliberately small and
# human-curated — a coordinator judgment call, not inferred by a model.
DESTINATION_COUNCIL_EDITORS: dict[str, tuple[str, ...]] = {
    # Feed natives: the hook, the zero-context stranger, the last line that gets carried away.
    "linkedin-post": ("puri", "cold-reader", "closer"),
    "linkedin-carousel": ("puri", "structure-editor"),
    "x-thread": ("puri", "closer", "cold-reader"),
    # Audience/long natives: architecture, idea density, earned specifics.
    "newsletter": ("perell", "cold-reader", "closer"),
    "blog": ("structure-editor", "perell", "specificity-auditor"),
    # Decision-maker natives: claims under weight, durable reasoning.
    "executive-brief": ("specificity-auditor", "structure-editor", "housel"),
    # Spoken/send natives.
    "talk-track": ("closer", "cold-reader"),
    "email": ("perell", "puri"),
}

# Unknown destinations still get a council — with a generic judgment lineup, never silently
# exempted from the bar.
DEFAULT_DESTINATION_EDITORS: tuple[str, ...] = ("cold-reader", "structure-editor")

# Alias normalization — mirrors web/lib/pieces/derivatives.ts's DERIVATIVE_FORMATS destinations,
# absorbing the free-form ``destination`` strings create-child/commit-idea accept.
_DESTINATION_ALIASES: dict[str, str] = {
    "linkedin-post": "linkedin-post",
    "linkedin": "linkedin-post",
    "li": "linkedin-post",
    "linkedin-carousel": "linkedin-carousel",
    "carousel": "linkedin-carousel",
    "x-thread": "x-thread",
    "x": "x-thread",
    "twitter": "x-thread",
    "twitter-thread": "x-thread",
    "newsletter": "newsletter",
    "blog": "blog",
    "blog-post": "blog",
    "executive-brief": "executive-brief",
    "brief": "executive-brief",
    "whitepaper": "executive-brief",
    "white-paper": "executive-brief",
    "talk-track": "talk-track",
    "talk": "talk-track",
    "speaker-notes": "talk-track",
    "email": "email",
    "email-update": "email",
}


def canonical_destination(destination: str) -> str | None:
    """Normalize a free-form destination string to its canonical format id (None when unknown).
    Whitespace runs fold to hyphens so 'LinkedIn Post' and 'linkedin-post' match alike."""
    key = " ".join((destination or "").split()).lower().replace(" ", "-")
    if not key:
        return None
    return _DESTINATION_ALIASES.get(key)


def destination_fit_editors(destination: str) -> tuple[str, ...]:
    """The destination-specific editors for a native (generic fallback for unknown destinations)."""
    canonical = canonical_destination(destination)
    if canonical is None:
        return DEFAULT_DESTINATION_EDITORS
    return DESTINATION_COUNCIL_EDITORS.get(canonical, DEFAULT_DESTINATION_EDITORS)


def derivative_council_editors(destination: str) -> tuple[str, ...]:
    """The full council lineup for one derivative: mandatory editors + universal hard-gate editors
    + the destination-specific judgment, deduped in that precedence order. The same ordering a
    human reads the council record in — the universal gates first, destination nuance after."""
    selected: list[str] = list(_MANDATORY_ORDER)
    for editor in UNIVERSAL_HARD_GATES.values():
        if editor not in selected:
            selected.append(editor)
    for editor in destination_fit_editors(destination):
        if editor not in selected:
            selected.append(editor)
    # Sanity: the Council model's invariant says the mandatory editors are always present.
    assert MANDATORY_EDITORS <= set(selected)
    return tuple(selected)


@dataclass
class DerivativeGateResult:
    """The publish-time quality gate for one derivative piece.

    ``required`` is False (and ``cleared`` trivially True) for anything that is not a derivative
    piece — anchors and legacy pieces are gated by their own existing flows, not this one.
    """

    required: bool
    cleared: bool
    bar: float = DERIVATIVE_QUALITY_BAR
    aggregate: float | None = None
    council_revision: str | None = None
    reasons: list[str] = field(default_factory=list)


async def derivative_publish_gate(store: WorkStateStore, piece: Piece) -> DerivativeGateResult:
    """Evaluate whether a derivative piece may publish: its OWN council at >= 9/10 against the
    revision about to ship, no universal hard gate tripped, no open clearances.

    Mirrors the approval-invalidation semantics of :mod:`app.release.approval`: a council that
    scored an older revision certifies nothing about the current one.
    """
    if piece.role not in (PieceRole.derivative, PieceRole.derivative.value):
        return DerivativeGateResult(required=False, cleared=True)

    reasons: list[str] = []
    council: Council | None = None

    if not piece.latest_council_id:
        reasons.append(
            "no council on record — every publishable derivative must clear its own council at "
            f"{DERIVATIVE_QUALITY_BAR:g}/10 before publishing"
        )
    else:
        council = await store.councils.get(piece.latest_council_id)
        if council is None:
            reasons.append("the recorded council result no longer exists — re-run the council")

    if council is not None:
        if council.revision != piece.latest_revision:
            reasons.append(
                f"the council scored revision {council.revision[:10]} but the current revision is "
                f"{(piece.latest_revision or 'none')[:10]} — the score does not certify what would ship"
            )
        aggregate = council.aggregate if council.aggregate is not None else 0.0
        if aggregate < DERIVATIVE_QUALITY_BAR:
            reasons.append(
                f"council aggregate {aggregate:g}/10 is below the {DERIVATIVE_QUALITY_BAR:g} "
                "derivative bar"
            )
        capped_by = sorted(
            {
                s.editor
                for s in council.editor_scores
                if s.hard_cap_applied and s.editor in UNIVERSAL_HARD_GATES.values()
            }
        )
        for editor in capped_by:
            gate = next(name for name, who in UNIVERSAL_HARD_GATES.items() if who == editor)
            reasons.append(
                f"universal hard gate failed: {gate} ({editor} applied a hard cap — hard gates "
                "apply to every destination regardless of score)"
            )

    if piece.open_clearances:
        reasons.append(
            f"{piece.open_clearances} open clearance(s) — the safety hard gate blocks external "
            "publication until they are granted (same block external sharing uses)"
        )

    return DerivativeGateResult(
        required=True,
        cleared=not reasons,
        aggregate=(council.aggregate if council is not None else None),
        council_revision=(council.revision if council is not None else None),
        reasons=reasons,
    )
