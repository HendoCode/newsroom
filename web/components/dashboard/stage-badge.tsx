import { Badge } from "@/components/ui/badge";
import { spikeStatusLabel, stageLabel } from "@/lib/dashboard/actions";
import type { PieceStage, SpikeStatus } from "@/lib/dashboard/types";
import { LOOP_STAGES } from "@/lib/pieces/stage";

/**
 * The stage badge shown on every card — one of the 9 piece states (domain model §1.9) or a spike
 * pool status (§1.6). Batch stages (drafting / council / incorporating / finalizing) are the
 * machine's background jobs; they read visually distinct (outline) from the human/interactive
 * stages so a scanner can tell "the machine is working" from "it's on a human". Purely token-driven.
 */

const BATCH_STAGES = new Set<PieceStage>(["drafting", "council", "incorporating", "finalizing"]);

// The review-loop stages (agents/app/models/piece.py §1.9: council ⇄ review ⇄ incorporating) all
// carry the identical round number in the wire data (PieceDetail.review_round /
// QueueItem.review_round) — gating display on `stage === "review"` alone was never a deliberate
// loop-vs-non-loop decision, just the first stage this was written against. A piece mid-loop in
// council or incorporating carries the same round number and deserves the same label. `LOOP_STAGES`
// is the same set the Pipeline rail's loop bracket uses (`lib/pieces/stage.ts`'s `STAGE_CLUSTER`) —
// one canonical source, not a second hand-maintained copy.

export function StageBadge({ stage, round }: { stage: PieceStage; round?: number | null }) {
  const variant = BATCH_STAGES.has(stage) ? "outline" : "secondary";
  const label = stageLabel(stage);
  return (
    <Badge variant={variant}>
      {label}
      {LOOP_STAGES.has(stage) && round ? ` · round ${round}` : null}
    </Badge>
  );
}

export function SpikeStatusBadge({ status }: { status: SpikeStatus }) {
  return <Badge variant="outline">{spikeStatusLabel(status)}</Badge>;
}
