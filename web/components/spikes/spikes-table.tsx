"use client";

import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  convergenceLabel,
  convergencePercent,
  mapsToLabel,
  originLabel,
  outcomeLabel,
  spikeStatusLabel,
} from "@/lib/spikes/format";
import type { Spike } from "@/lib/spikes/types";

/**
 * The spike table (cmw-ui-wireframes screen 5): headline, convergence (bar + number), maps-to,
 * outcome, creator · origin, status, and a per-row primary action. Ownership is attribution, not
 * a lock (D15) — the row action is offered regardless of who created the spike.
 */
export function SpikesTable({
  spikes,
  selectedId,
  onSelect,
  voiceHint,
}: {
  spikes: Spike[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  /** The Voice the caller last ran (e.g. the Radar's own selector) — carried onto "Pick &amp;
   * assign" as `?voice=` so kickoff defaults to it instead of the brain's first voice
   * alphabetically (cmw-first-run-ux-batch item 7). Omitted where there's no such context (e.g.
   * the plain Spikes &amp; Vault browser). */
  voiceHint?: string;
}) {
  if (spikes.length === 0) {
    return (
      <div className="rounded-lg border border-dashed bg-card p-6 text-center">
        <p className="font-serif text-lg font-semibold">Nothing here</p>
        <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
          No spikes match the current tab/filters.
        </p>
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-lg border bg-card">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b bg-muted/40 text-left text-xs uppercase tracking-wide text-muted-foreground">
            <th className="px-4 py-2 font-medium">Spike</th>
            <th className="px-4 py-2 font-medium">Convergence</th>
            <th className="px-4 py-2 font-medium">Maps to</th>
            <th className="px-4 py-2 font-medium">Outcome</th>
            <th className="px-4 py-2 font-medium">Creator · origin</th>
            <th className="px-4 py-2 font-medium">Status</th>
            <th className="px-4 py-2 font-medium" />
          </tr>
        </thead>
        <tbody>
          {spikes.map((spike) => {
            const pct = convergencePercent(spike.convergence_score);
            return (
              <tr
                key={spike.id}
                onClick={() => onSelect(spike.id)}
                aria-selected={selectedId === spike.id}
                className={
                  "cursor-pointer border-b last:border-0 " +
                  (selectedId === spike.id ? "bg-accent/50" : "hover:bg-muted/30")
                }
              >
                <td className="px-4 py-3">
                  <div className="font-medium">{spike.headline}</div>
                </td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    <span className="h-2 w-16 overflow-hidden rounded-full border bg-background">
                      {pct != null ? (
                        <span className="block h-full bg-primary" style={{ width: `${pct}%` }} />
                      ) : null}
                    </span>
                    <span className="text-muted-foreground">
                      {convergenceLabel(spike.convergence_score)}
                    </span>
                  </div>
                </td>
                <td className="px-4 py-3 text-muted-foreground">{mapsToLabel(spike)}</td>
                <td className="px-4 py-3 text-muted-foreground">{outcomeLabel(spike)}</td>
                <td className="px-4 py-3 text-muted-foreground">
                  {spike.creator} · {originLabel(spike.origin.kind)}
                </td>
                <td className="px-4 py-3">
                  <Badge variant="outline">{spikeStatusLabel(spike.status)}</Badge>
                </td>
                <td className="px-4 py-3">
                  {spike.piece_id ? (
                    <Button asChild size="sm" variant="outline" onClick={(e) => e.stopPropagation()}>
                      <Link href={`/pieces/${spike.piece_id}`}>Open piece</Link>
                    </Button>
                  ) : spike.status === "vaulted" ? (
                    <Button asChild size="sm" variant="outline" onClick={(e) => e.stopPropagation()}>
                      <Link
                        href={
                          voiceHint
                            ? `/spikes/${spike.id}?voice=${encodeURIComponent(voiceHint)}`
                            : `/spikes/${spike.id}`
                        }
                      >
                        Re-consider
                      </Link>
                    </Button>
                  ) : (
                    <Button asChild size="sm" onClick={(e) => e.stopPropagation()}>
                      <Link
                        href={
                          voiceHint
                            ? `/spikes/${spike.id}?voice=${encodeURIComponent(voiceHint)}`
                            : `/spikes/${spike.id}`
                        }
                      >
                        Pick &amp; assign
                      </Link>
                    </Button>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
