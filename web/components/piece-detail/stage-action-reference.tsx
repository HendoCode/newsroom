import { stageLabel } from "@/lib/dashboard/actions";
import { STAGE_ACTION_REFERENCE } from "@/lib/pieces/actions";
import { RAIL_STAGES } from "@/lib/pieces/stage";
import type { PieceStage } from "@/lib/pieces/types";
import { cn } from "@/lib/utils";

const ORDER: readonly PieceStage[] = [...RAIL_STAGES, "paused"];

/** The stage → primary-action reference table (cmw-ui-wireframes screen 2 right panel) — the full
 * mapping, so the "one action per stage" rule stays legible even though only the current stage's
 * action renders as the actionable "Next action" card above. */
export function StageActionReference({ current }: { current: PieceStage }) {
  return (
    <table className="w-full text-sm">
      <tbody>
        {ORDER.map((stage) => (
          <tr
            key={stage}
            className={cn("border-b last:border-0", stage === current && "bg-accent/60")}
          >
            <td className="py-1.5 pr-3 font-medium">
              {stageLabel(stage)}
              {stage === current ? <span className="sr-only"> (current)</span> : null}
            </td>
            <td className="py-1.5 text-muted-foreground">{STAGE_ACTION_REFERENCE[stage]}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
