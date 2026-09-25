import * as React from "react";

import { STAGE_CLUSTER, type RailStage, type StageCluster } from "@/lib/pieces/stage";
import type { PieceStage } from "@/lib/dashboard/types";
import { cn } from "@/lib/utils";

const CLUSTER_ORDER: readonly StageCluster[] = ["intake", "loop", "ship"];

/**
 * The dashboard queue's compact echo of the piece-detail Pipeline rail (cmw-pipeline-depiction-
 * design decision C, refined live by Hendo — not a plain dot-meter: "having the dots connected by
 * horizontal lines would help"). Three short segments for the SAME intake/loop/ship grouping the
 * full rail uses (`lib/pieces/stage.ts`'s `STAGE_CLUSTER`), joined by connecting lines, so a card
 * shows "how far through the whole pipeline," not just "where," without the ~40px-per-row cost a
 * full per-stage rail would add to this deliberately dense list (PR #89). Purely decorative
 * (`aria-hidden` — the adjacent `StageBadge` text carries the real accessible state); renders
 * nothing for `paused` (off-rail — no cluster position, same as the main rail's own paused chip)
 * or a spike item (no stage at all).
 */
export function PipelineMiniRail({
  stage,
  round,
}: {
  stage: PieceStage | null;
  round: number | null;
}) {
  if (stage === null || stage === "paused") return null;
  const railStage: RailStage = stage === "published" ? "released" : (stage as RailStage);
  const currentCluster = STAGE_CLUSTER[railStage];
  const currentIndex = CLUSTER_ORDER.indexOf(currentCluster);
  const looping = currentCluster === "loop" && (round ?? 0) > 1;

  return (
    <span
      className="inline-flex items-center"
      aria-hidden
      title={`Pipeline: ${currentCluster} stage${looping ? ` · loop ${(round ?? 1) - 1}×` : ""}`}
    >
      {CLUSTER_ORDER.map((cluster, i) => (
        <React.Fragment key={cluster}>
          {i > 0 ? <span className="h-px w-1.5 bg-border" /> : null}
          <span
            className={cn(
              "h-1.5 w-4 rounded-full",
              i < currentIndex && "bg-secondary",
              i === currentIndex && (looping ? "bg-accent" : "bg-primary"),
              i > currentIndex && "border border-border",
            )}
          />
        </React.Fragment>
      ))}
    </span>
  );
}
