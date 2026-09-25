/**
 * The stage rail (cmw-ui-wireframes screen 2): the 9-state machine (domain model §1.9), rendered
 * as 8 inline steps in their settled canonical order plus `paused` as a distinct off-rail chip —
 * mirroring the wireframe's own note that "`paused` is an off-rail state reachable from any
 * interactive step (stop-for-the-day)", not a forward step in the pipeline.
 */

import type { PieceStage } from "@/lib/pieces/types";

export const RAIL_STAGES = [
  "interviewing",
  "drafting",
  "council",
  "review",
  "incorporating",
  "finalizing",
  "finalized",
  "lessons",
  "released",
] as const satisfies readonly PieceStage[];

/** The stages that have a position on the linear rail (everything except `paused`). */
export type RailStage = (typeof RAIL_STAGES)[number];

/** Batch stages run as background jobs that flip status (§1.9); everything else waits on a human.
 * Drives the rail's "double border" batch styling (cmw-ui-wireframes screen 2 legend). */
export const BATCH_STAGES: ReadonlySet<PieceStage> = new Set<PieceStage>([
  "drafting",
  "council",
  "incorporating",
  "finalizing",
]);

export function isBatchStage(stage: PieceStage): boolean {
  return BATCH_STAGES.has(stage);
}

/**
 * Which of the three visual groups a rail stage belongs to (Pipeline redesign,
 * cmw-pipeline-depiction-design report's "Evolving the pipeline" proposal): the rail draws the
 * loop bracket/round chip from this declaration rather than hand-positioned SVG, so a future
 * stage inserted into (or removed from) the review loop only needs to say which cluster it's in.
 */
export type StageCluster = "intake" | "loop" | "ship";

export const STAGE_CLUSTER: Record<RailStage, StageCluster> = {
  interviewing: "intake",
  drafting: "intake",
  council: "loop",
  review: "loop",
  incorporating: "loop",
  finalizing: "ship",
  finalized: "ship",
  lessons: "ship",
  released: "ship",
};

/** The stages of `RAIL_STAGES` belonging to `cluster`, in canonical order. */
export function stagesInCluster(cluster: StageCluster): RailStage[] {
  return RAIL_STAGES.filter((s) => STAGE_CLUSTER[s] === cluster);
}

/** The review-loop stages (`council ⇄ review ⇄ incorporating`) — the single source of truth for
 * "does this stage carry a round number," derived from `STAGE_CLUSTER` rather than a second
 * hand-maintained set, so a future stage added to (or removed from) the loop can't update one
 * without the other. */
export const LOOP_STAGES: ReadonlySet<PieceStage> = new Set(stagesInCluster("loop"));

export type RailStepState = "done" | "current" | "upcoming";

/**
 * Per-step render state for the 8 inline rail stages. When the piece is `paused`, no rail step is
 * "current" — the caller renders the Paused chip as the current element instead (paused has no
 * single position on the linear rail: it is reachable from either `interviewing` or `review`, and
 * `resume` always lands back on `interviewing` regardless of which one it was).
 */
/** True for the terminal ship state, including the legacy `published` wire value. */
export function isReleasedStage(stage: PieceStage | string | null | undefined): boolean {
  return stage === "released" || stage === "published";
}

export function railStepStates(stage: PieceStage): Record<RailStage, RailStepState> {
  const normalized: PieceStage = stage === "published" ? "released" : stage;
  const currentIndex = normalized === "paused" ? -1 : RAIL_STAGES.indexOf(normalized as RailStage);
  const result = {} as Record<RailStage, RailStepState>;
  for (const [i, s] of RAIL_STAGES.entries()) {
    result[s] = i < currentIndex ? "done" : i === currentIndex ? "current" : "upcoming";
  }
  return result;
}
