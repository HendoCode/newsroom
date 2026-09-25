/**
 * Resolving a Spike's origin back to the Narrative that produced it (§1.5/§1.6).
 *
 * `SpikeOrigin.ref` is overloaded (an OracleRun/Job id, a Narrative id, or absent for a tangent —
 * see `agents/app/models/spike.py`'s `SpikeOrigin` docstring) — it is only ever a Narrative id
 * when `kind === "narrative"`. Shared by `spike-kickoff.tsx` (the original "View the narrative
 * that produced this spike" reveal, PR #79) and `app/pieces/[pieceId]/page.tsx` (surfacing the
 * same narrative from the piece itself, cmw-archive-piece) so neither re-derives this check.
 */

import type { Spike } from "@/lib/spikes/types";

/** The narrative id behind `spike`, or `null` if it wasn't seeded from a spoken narrative. */
export function originNarrativeId(spike: Pick<Spike, "origin">): string | null {
  return spike.origin.kind === "narrative" && spike.origin.ref ? spike.origin.ref : null;
}
