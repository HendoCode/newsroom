/**
 * The "needs my action" predicate (cmw-open-decisions report §Item-3, the settled predicate).
 *
 * This is an ATTRIBUTION-DRIVEN convenience filter, **never a permission gate** (§1.17, flat
 * authorization). It answers only "did this land on *my* plate?" by comparing the signed-in user's
 * email against the piece/spike's attribution facts. Anything it hides is still fully actionable
 * from the "All in flight" tab — nothing here denies anyone access.
 *
 * The predicate is the union of the settled branches, keyed on
 * `(stage, the user's attributed relationship to the piece)`:
 *   1. interviewing + assigned expert on an OPEN interview                  (assigned-expert)
 *   2. interviewing + assigned expert invited but no open interview yet     (assigned-expert · unanswered invite)
 *   3. interviewing + owner + some interview marked complete                (owner · "enough input")
 *   4. interviewing + owner + open GAPs routed back from council            (owner · GAP loop-back)
 *   5. review + owner                                                       (owner)
 *   6. any stage + a failed/stuck job the user triggered                    (last-actor · Item 4)
 *   7. incorporating + owner                                                (owner)
 *   8. paused + owner                                                       (owner · stale paused)
 *   9. finalized + owner + lessons proposed & unreviewed                    (owner · D12)
 *  10. finalized + owner + no pending lessons                               (owner · publish-ready)
 *  11. lessons + owner                                                      (owner · pending lessons)
 *  12. a picked-but-unassigned spike the user created                       (coordinator · use case C)
 */

import type { QueueItem } from "@/lib/dashboard/types";

/** The attributed relationship that put an item on the user's plate — display/sort only. */
export type Relationship =
  | "assigned-expert"
  | "owner"
  | "last-actor"
  | "coordinator";

export interface NeedsActionResult {
  relationship: Relationship;
  /** The "Why here" line shown on the card, naming the attribution relationship. */
  why: string;
}

/**
 * Whether `item` needs `email`'s action, and why. Returns `null` when it does not (which is NOT a
 * statement about access — the user can still act on it from "All in flight"). Pure and total:
 * a falsy/blank email never matches anything.
 */
export function needsMyAction(email: string | null | undefined, item: QueueItem): NeedsActionResult | null {
  if (!email) return null;

  // 6 · A failed/stuck batch job the user triggered. Checked first: the most urgent thing on a
  // plate, and it can co-occur with an ownership branch (you own it AND you fired the failed job).
  if (item.failed_job && item.failed_job.triggered_by === email) {
    return {
      relationship: "last-actor",
      why: `A ${item.failed_job.type} job you triggered failed (${item.failed_job.code}) — the piece stayed at its last stable stage; retry or edit inputs.`,
    };
  }

  if (item.kind === "piece") {
    // 1 · Assigned expert on an open interview.
    if (
      item.stage === "interviewing" &&
      item.open_interviews.some((iv) => iv.expert === email)
    ) {
      return {
        relationship: "assigned-expert",
        why: "You are the assigned expert on an open interview.",
      };
    }

    // 2 · Assigned expert who has been invited but has no open interview yet (unanswered invite).
    if (
      item.stage === "interviewing" &&
      item.assigned_experts.includes(email) &&
      !item.open_interviews.some((iv) => iv.expert === email)
    ) {
      return {
        relationship: "assigned-expert",
        why: "You have been assigned as an expert — accept the open interview invite.",
      };
    }

    // 3 · Owner deciding "enough input" (an interview is marked complete — a signal, not a trigger).
    if (
      item.stage === "interviewing" &&
      item.owner === email &&
      item.has_complete_interview
    ) {
      return {
        relationship: "owner",
        why: "You own this piece and an interview is marked complete — decide “enough input” and draft.",
      };
    }

    // 4 · Owner of a piece routed back to interviewing with open GAPs from the council/review loop.
    if (
      item.stage === "interviewing" &&
      item.owner === email &&
      item.open_gaps > 0
    ) {
      return {
        relationship: "owner",
        why: `You own this piece and ${item.open_gaps} open GAP${item.open_gaps === 1 ? "" : "s"} routed back from review — open or close the gap interview${item.open_gaps === 1 ? "" : "s"}.`,
      };
    }

    // 5 · Owner of a piece in review.
    if (item.stage === "review" && item.owner === email) {
      return {
        relationship: "owner",
        why: "You own a piece in review — mint/collect a Doc, close the round, or finalize.",
      };
    }

    // 7 · Owner of a piece being incorporated.
    if (item.stage === "incorporating" && item.owner === email) {
      return {
        relationship: "owner",
        why: "You own a piece that is incorporating review feedback — wait for it, or check progress.",
      };
    }

    // 8 · Owner of a paused piece.
    if (item.stage === "paused" && item.owner === email) {
      return {
        relationship: "owner",
        why: "You own a paused piece — resume when you are ready.",
      };
    }

    // 9 / 10 · Owner of a finalized piece: lessons to review, or publish-ready.
    if (item.stage === "finalized" && item.owner === email) {
      if (item.lessons_proposed > 0) {
        return {
          relationship: "owner",
          why: `You own a finalized piece with ${item.lessons_proposed} proposed lessons awaiting your accept/reject (D12).`,
        };
      }
      return {
        relationship: "owner",
        why: "You own a finalized piece that is ready to publish.",
      };
    }

    // 11 · Owner of a piece in the lessons stage.
    if (item.stage === "lessons" && item.owner === email) {
      return {
        relationship: "owner",
        why: "You own a piece with pending lessons — accept, edit, or reject them.",
      };
    }

    return null;
  }

  // 12 · Coordinator on a picked-but-unassigned spike they created.
  if (
    item.kind === "spike" &&
    item.spike_status === "picked" &&
    !item.spike_assigned &&
    item.creator === email
  ) {
    return {
      relationship: "coordinator",
      why: "You picked a spike but haven't assigned an expert / kicked off the interview (use case C).",
    };
  }

  return null;
}
