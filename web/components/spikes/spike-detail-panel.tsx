import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { convergenceLabel, originLabel } from "@/lib/spikes/format";
import type { Spike } from "@/lib/spikes/types";

/**
 * The selected-spike detail (cmw-ui-wireframes screen 5): rank rationale, convergence note, and
 * source/origin, plus the primary hand-off action. Ownership is attribution, not a lock (D15).
 */
export function SpikeDetailPanel({ spike }: { spike: Spike }) {
  return (
    <div className="grid gap-4 lg:grid-cols-[1fr,320px]">
      <Card>
        <CardHeader>
          <CardTitle className="text-xl">&ldquo;{spike.headline}&rdquo;</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-2 text-sm text-muted-foreground">
          {spike.rank_rationale ? (
            <div>
              <b className="text-foreground">Rank rationale:</b> {spike.rank_rationale}
            </div>
          ) : null}
          {spike.convergence_note ? (
            <div>
              <b className="text-foreground">Convergence note:</b> {spike.convergence_note}
            </div>
          ) : null}
          <div>
            <b className="text-foreground">Convergence:</b> {convergenceLabel(spike.convergence_score)}
          </div>
          <div>
            <b className="text-foreground">Creator:</b> {spike.creator} ·{" "}
            <b className="text-foreground">Origin:</b> {originLabel(spike.origin.kind)}
          </div>
          {spike.intent?.audience || spike.intent?.angle ? (
            <div>
              <b className="text-foreground">Carried intent:</b>{" "}
              {[spike.intent.audience, spike.intent.angle].filter(Boolean).join(" — ")}
            </div>
          ) : null}

          <div className="mt-2">
            {spike.piece_id ? (
              <Button asChild>
                <Link href={`/pieces/${spike.piece_id}`}>Open piece</Link>
              </Button>
            ) : (
              <Button asChild>
                <Link href={`/spikes/${spike.id}`}>Pick &amp; assign expert</Link>
              </Button>
            )}
          </div>
        </CardContent>
      </Card>

      <div className="flex flex-col gap-3">
        <div className="rounded-md border border-dashed bg-muted/30 px-3 py-2 text-sm text-muted-foreground">
          <b className="text-foreground">Nothing is thrown away.</b> Unused spikes stay in the
          Vault with their convergence scoring, so they can be picked later once a named account
          or a real metric attaches. Tangents parked from interviews land here too.
        </div>
        <div className="rounded-md border border-dashed bg-muted/30 px-3 py-2 text-sm text-muted-foreground">
          <b className="text-foreground">Status set (D15):</b> proposed → picked → in-flight →
          vaulted. Picking a spike is what creates a piece (stage{" "}
          <span className="font-mono">interviewing</span>); the spike stays attributed to its
          original creator even when someone else picks it.
        </div>
      </div>
    </div>
  );
}
