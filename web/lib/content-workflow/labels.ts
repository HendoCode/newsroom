/**
 * Operator-facing English for content-workflow wire values.
 *
 * Internal enum names (`HumanObligationKind`, `CommandKind`, `PieceRole`, phase slugs) stay in
 * code and APIs only — never greet a teammate as raw `confirm-input-sufficiency` text. A
 * `Record<Union, string>` here is the compile-time canary: adding a kind without a label fails
 * `tsc --noEmit`.
 */

import type { HumanObligationKind, PieceRole } from "@/lib/content-workflow/types";

export const OBLIGATION_KIND_LABELS: Record<HumanObligationKind, string> = {
  "choose-direction": "Choose a direction",
  "answer-question": "Answer a question",
  "approve-contribution": "Approve a contribution",
  "confirm-input-sufficiency": "Decide if there's enough to draft",
  "resolve-gap": "Fill a gap",
  "correct-claim": "Correct a claim",
  "grant-clearance": "Grant clearance",
  "close-review": "Close a review",
  "revise-final": "Revise the final draft",
  "accept-final-revision": "Accept the final revision",
  "authorize-release": "Authorize release",
  "decide-lesson": "Decide a lesson",
  "decide-abandonment": "Decide whether to stop",
  "attention-required": "Needs attention",
  recover_failure: "Recover a failure",
  pick_idea: "Pick an idea",
};

export function obligationKindLabel(kind: string): string {
  return OBLIGATION_KIND_LABELS[kind as HumanObligationKind] ?? humanizeSlug(kind);
}

const PROJECT_PHASE_LABELS: Record<string, string> = {
  shaping: "Shaping",
  "building-evidence": "Gathering evidence",
  producing: "Producing",
  "final-mile": "Final mile",
  completed: "Completed",
  abandoned: "Stopped",
};

const PIECE_PHASE_LABELS: Record<string, string> = {
  planned: "Planned",
  "input-building": "Gathering input",
  drafting: "Drafting",
  "quality-closure": "In review",
  "human-revision": "Human revision",
  "release-ready": "Ready to publish",
  released: "Published",
  abandoned: "Stopped",
};

export function phaseLabel(phase: string): string {
  return PROJECT_PHASE_LABELS[phase] ?? PIECE_PHASE_LABELS[phase] ?? humanizeSlug(phase);
}

export const PIECE_ROLE_LABELS: Record<PieceRole, string> = {
  anchor: "Main piece",
  derivative: "Follow-on piece",
};

export function pieceRoleLabel(role: string): string {
  return PIECE_ROLE_LABELS[role as PieceRole] ?? humanizeSlug(role);
}

/** Last-resort: `confirm-input-sufficiency` → "Confirm input sufficiency", never the raw slug. */
export function humanizeSlug(value: string): string {
  const spaced = value.replace(/[_-]+/g, " ").trim();
  if (!spaced) return value;
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}
