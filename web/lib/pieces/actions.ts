/**
 * Stage-contextual actions for the piece-detail screen (cmw-ui-wireframes screen 2): the "Next
 * action" card (one PRIMARY action per state — the requirement Item 2 and the brief both call
 * out) plus the small set of secondary actions the wireframe keeps visually distinct ("Reviews
 * done" vs "Finalize" must never be conflated, Item 7; pause is always a secondary control, never
 * the primary one).
 *
 * Pure and total over `PieceStage` — every branch maps to exactly one real orchestration trigger
 * (`agents/app/orchestration/routes.py`) or an honest "running…" / informational state; nothing
 * here is a permission gate (flat auth, §1.17) — any signed-in user may fire any legal trigger.
 */

import type { PieceTrigger } from "@/lib/agents-client";
import type { PieceDetail, PieceStage } from "@/lib/pieces/types";

export type NextAction =
  | { kind: "trigger"; trigger: PieceTrigger; label: string; description: string; chip?: ActionChip }
  | { kind: "running"; label: string; description: string }
  | { kind: "info"; label: string; description: string }
  | { kind: "link"; href: string; label: string; description: string }
  | { kind: "propose-lessons"; label: string; description: string };

/** A short, non-interactive badge rendered with equal visual weight next to the primary action
 * button (Pipeline redesign decision A: "keep Publish primary; give the pending-lessons chip
 * equal visual weight next to it") — informational only, never a second control; the real action
 * it names stays a `secondaryActions` entry (e.g. "Capture lessons"). */
export interface ActionChip {
  label: string;
}

export type SecondaryAction =
  | { kind: "trigger"; trigger: PieceTrigger; label: string; description: string }
  | { kind: "link"; href: string; label: string; description: string }
  | { kind: "open-interview-round"; label: string; description: string; roundNumber: number };

/** The stage→action reference table (cmw-ui-wireframes screen 2 right panel) — informational,
 * distinct from the single "Next action" primary button below. */
export const STAGE_ACTION_REFERENCE: Record<PieceStage, string> = {
  interviewing: "Open interview / “Enough input” → draft",
  drafting: "running… (or Retry if failed)",
  council: "running…",
  review: "Open review round (mint · preview · confirm) · Finalize · Another interview round",
  incorporating: "running…",
  finalizing: "rendering…",
  finalized: "Capture lessons · Re-export · Publish",
  lessons: "Accept / edit / reject",
  paused: "Resume",
  released: "Anchor shipped — durable public links in Outputs; next beat is Derivatives",
  published: "Anchor shipped — durable public links in Outputs; next beat is Derivatives",
};

function hasFailedJobType(piece: PieceDetail, jobType: string): boolean {
  return piece.failures.some((f) => f.type === jobType);
}

/** The ONE stage-contextual primary action for `piece`'s current stage. */
export function nextAction(piece: PieceDetail): NextAction {
  switch (piece.stage) {
    case "interviewing":
      return {
        kind: "trigger",
        trigger: "enough-input",
        label: hasFailedJobType(piece, "draft") ? "Retry — enough input → draft" : "Enough input → draft",
        description:
          "A human with authority over this piece decides the accumulated interview input is " +
          "sufficient and presses draft — an interview marked complete is only a signal.",
      };
    case "drafting":
      return {
        kind: "running",
        label: "Drafting…",
        description: "The draft job is running as a background batch step.",
      };
    case "council":
      return {
        kind: "running",
        label: "Council running…",
        description: "One scoring pass against the current revision — mandatory editors always run.",
      };
    case "review":
      return {
        kind: "link",
        href: `/pieces/${encodeURIComponent(piece.id)}/review`,
        label: "Open review round",
        description:
          "Mint a Doc, preview exactly what a “reviews done” would fold in, and only then confirm " +
          "— never a blind fire. Finalize is a distinct action below, never conflated with closing " +
          "a round (Item 7).",
      };
    case "incorporating":
      return {
        kind: "running",
        label: "Incorporating edits…",
        description: "Folding in this round's feedback into a new revision, then re-running council.",
      };
    case "finalizing":
      return {
        kind: "running",
        label: "Rendering…",
        description: "Injecting the semantic draft into the branded template (HTML, PDF, clean Doc).",
      };
    case "finalized": {
      // `publish` (finalized → published) is the primary action here — it's the actual exit from
      // "in flight" (Hendo's complaint this stage exists to fix). `capture-lessons` moves to
      // secondaryActions below: it's independent of publishing, not a prerequisite (see
      // agents/app/models/piece.py's ALLOWED_TRANSITIONS comment) — either order is legal.
      //
      // A piece can carry proposed lessons here independent of ever having entered the `lessons`
      // stage (IncorporateStep's mid-pipeline propose_from_review_edits) — this branch used to
      // never look, while the dashboard's own primaryAction (lib/dashboard/actions.ts) already
      // checks lessons_proposed for the identical case. Mirrored here as a `chip` (Pipeline
      // redesign decision A) rather than folded into the prose, so it renders with equal visual
      // weight next to Publish instead of competing with it for the reader's attention.
      const pendingLessons = piece.lessons.filter((l) => l.status === "proposed").length;
      return {
        kind: "trigger",
        trigger: "publish",
        label: "Authorize release",
        description:
          "The human AuthorizeRelease: mints durable public links (branded HTML/PDF in S3, an " +
          "externally-shared Google Doc) as immutable Publication Release #1 and moves the " +
          "piece to Released. The machine never does this on its own. A circulating link can't " +
          "be un-shared; further releases are numbered and append-only.",
        ...(pendingLessons > 0
          ? {
              chip: {
                label: `${pendingLessons} lesson${pendingLessons === 1 ? "" : "s"} awaiting accept/reject`,
              },
            }
          : {}),
      };
    }
    case "lessons": {
      // Three genuinely different states, not one `proposed === 0` check: never proposed yet,
      // proposals still awaiting accept/edit/reject, and every proposal already resolved.
      const unresolved = piece.lessons.filter((l) => l.status === "proposed").length;
      const everProposed = piece.lessons.length > 0;
      if (unresolved > 0) {
        return {
          kind: "link",
          href: "/voice-kit",
          label: `Resolve ${unresolved} pending lesson${unresolved === 1 ? "" : "s"}`,
          description:
            "Accept, edit, or reject each proposed lesson on the voice kit's lessons gate " +
            "before finishing this round — the machine never self-commits.",
        };
      }
      if (everProposed) {
        return {
          kind: "trigger",
          trigger: "finish-lessons",
          label: "Finish lessons",
          description:
            "Closes this round — every proposed lesson has been accepted, edited, or rejected.",
        };
      }
      return {
        kind: "propose-lessons",
        label: "Propose lessons",
        description:
          "Diffs the machine's final draft against what was actually published and proposes " +
          "generalizable per-voice lessons (Opus) — nothing to accept/edit/reject until this " +
          "runs at least once.",
      };
    }
    case "paused":
      return {
        kind: "trigger",
        trigger: "resume",
        label: "Resume",
        description: "Stop-for-the-day is resumable — returns the piece to interviewing.",
      };
    case "released":
    case "published":
      return {
        kind: "trigger",
        trigger: "publish",
        label: "Authorize another release",
        description:
          "Mints a new immutable numbered Publication Release from the current canonical " +
          "content. Prior releases are never overwritten — already-circulating links keep " +
          "resolving. The workspace stays open for follow-ons.",
      };
    default: {
      const exhaustive: never = piece.stage;
      throw new Error(`unhandled piece stage ${String(exhaustive)}`);
    }
  }
}

/** Secondary, visually distinct actions available alongside the primary one — never the same
 * button as `nextAction` (Item 7: "Reviews done" and "Finalize" must never be conflated). */
export function secondaryActions(piece: PieceDetail): SecondaryAction[] {
  const actions: SecondaryAction[] = [];
  if (piece.stage === "finalized") {
    // `capture-lessons` (finalized → lessons) is always legal here — nothing can be `proposed`
    // outside the `lessons` stage, so gating this on an existing proposal is a contradiction that
    // can never be true on real data. Independent of `publish` above — either order is legal, or
    // a piece can go through lessons more than once before ever publishing.
    const priorLessons = piece.lessons.length;
    actions.push({
      kind: "trigger",
      trigger: "capture-lessons",
      label: "Capture lessons",
      description:
        priorLessons > 0
          ? `Reopens the lessons loop for another round — ${priorLessons} lesson${priorLessons === 1 ? "" : "s"} recorded from earlier rounds.`
          : "Opens the lessons loop: diff what was actually published against the machine's " +
            "final draft and propose generalizable per-voice lessons.",
    });
  }
  if (piece.stage === "review") {
    actions.push({
      kind: "link",
      label: "Finalize",
      href: `/pieces/${encodeURIComponent(piece.id)}/finalize`,
      description:
        "Opens format selection + pre-finalize checks, then renders the branded output — " +
        "distinct from “Reviews done”.",
    });
  }
  if (piece.stage === "interviewing" || piece.stage === "review") {
    actions.push({
      kind: "trigger",
      trigger: "pause",
      label: "Stop for the day",
      description: "Pauses this interactive step; resumable any time.",
    });
  }
  if (piece.stage === "review") {
    // route_to_interview (agents/app/orchestration/machine.py) is legal only from council/review
    // — Hendo's deliberate entry point, chosen over the transient `drafting` stage so this can
    // never interrupt a running batch job. Every earlier round's transcript turns stay intact:
    // Interview sessions are additive on one piece-scoped transcript (§5-Q1), never replaced.
    const roundNumber = piece.interviews.length + 1;
    actions.push({
      kind: "open-interview-round",
      label: "Start another round of interviews",
      description:
        `Routes this piece back to interviewing and opens interview round ${roundNumber} — ` +
        "every earlier round stays recorded in the one shared transcript below.",
      roundNumber,
    });
  }
  return actions;
}
