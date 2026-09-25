/**
 * Stage-contextual primary action for a queue card (cmw-ui-wireframes §6.2 — "what do I do next"
 * must be unambiguous per stage) plus human-readable stage/status labels.
 *
 * The dashboard is the only screen built in this ticket; every other destination is a later ticket.
 * So an action either points at a REAL route (`href`) or is a clean SEAM (`href` undefined +
 * `hint`) the piece-detail / review / kickoff tickets will wire up. Pure and total.
 */

import type { NeedsActionResult } from "@/lib/dashboard/needs-my-action";
import type { PieceStage, QueueItem, SpikeStatus } from "@/lib/dashboard/types";

export interface PrimaryAction {
  label: string;
  /**
   * Where the action navigates. The interview case reaches a REAL v1 route; every other
   * destination is a placeholder seam page (`/pieces/*`, `/spikes/*`) following the repo's
   * established `/interviews/[id]` seam convention, so navigation always works and each seam names
   * the screen its ticket will build.
   */
  href: string;
}

/**
 * The single stage-contextual primary action for `item`. `email` lets the interviewing-expert case
 * deep-link to the viewer's own open interview (the one fully-built cross-screen route in v1).
 */
export function primaryAction(
  item: QueueItem,
  needs: NeedsActionResult | null,
  email: string | null | undefined,
): PrimaryAction {
  if (item.kind === "spike") {
    // A picked spike already has its piece (and, per cmw-piece-interviewing-without-interview, its
    // Interview) — "Assign expert & kick off" is the wrong label for it: it reads as an
    // assignment step still to do, when the assignment already happened. Reserve that label for a
    // spike nobody has picked yet.
    if (item.spike_assigned) {
      return { label: "Continue kickoff", href: `/spikes/${item.id}` };
    }
    // A vaulted spike was deliberately deferred — "Assign expert & kick off" reads as a fresh
    // candidate, misleading for something that was already assessed and set aside. Use a
    // lower-pressure label that still lets the coordinator re-open it.
    if (item.spike_status === "vaulted") {
      return { label: "Re-consider", href: `/spikes/${item.id}` };
    }
    return { label: "Assign expert & kick off", href: `/spikes/${item.id}` };
  }

  const detail = `/pieces/${item.id}`;

  // A failed/stuck job dominates the action regardless of stage (Item 4): retry / edit inputs.
  if (item.failed_job) {
    return { label: "Retry", href: detail };
  }

  switch (item.stage) {
    case "interviewing": {
      // The assigned expert deep-links straight into their own open interview (the SSO-gated route).
      if (needs?.relationship === "assigned-expert") {
        const mine = item.open_interviews.find((iv) => iv.expert === email) ?? item.open_interviews[0];
        return { label: "Open my interview", href: mine ? `/interviews/${mine.interview_id}` : detail };
      }
      return { label: "Review input & draft", href: detail };
    }
    case "drafting":
    case "council":
    case "incorporating":
    case "finalizing":
      return { label: "View progress", href: detail };
    case "review":
      return { label: "Open review round", href: detail };
    case "finalized":
      return item.lessons_proposed > 0
        ? { label: "Review lessons", href: detail }
        : { label: "View outputs", href: detail };
    case "lessons":
      return { label: "Review lessons", href: detail };
    case "paused":
      return { label: "Resume", href: detail };
    case "released":
    case "published":
      return { label: "View outputs", href: detail };
    default:
      return { label: "View piece", href: detail };
  }
}

const STAGE_LABELS: Record<PieceStage, string> = {
  interviewing: "Interviewing",
  drafting: "Drafting",
  council: "Council",
  review: "Review",
  incorporating: "Incorporating",
  finalizing: "Finalizing",
  finalized: "Finalized",
  lessons: "Lessons",
  paused: "Paused",
  released: "Released",
  published: "Released",
};

const SPIKE_STATUS_LABELS: Record<SpikeStatus, string> = {
  proposed: "Proposed",
  picked: "Picked",
  "in-flight": "In flight",
  vaulted: "Vaulted",
};

export function stageLabel(stage: PieceStage): string {
  return STAGE_LABELS[stage] ?? stage;
}

export function spikeStatusLabel(status: SpikeStatus): string {
  return SPIKE_STATUS_LABELS[status] ?? status;
}

const RELATIONSHIP_LABELS: Record<string, string> = {
  "assigned-expert": "assigned expert",
  owner: "owner",
  "last-actor": "last actor",
  coordinator: "coordinator",
};

export function relationshipLabel(relationship: string): string {
  return RELATIONSHIP_LABELS[relationship] ?? relationship;
}
