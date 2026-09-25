/**
 * Narrative domain types (domain model §1.5) — Oracle Entry B's seed (cmw-ui-wireframes screen 8).
 *
 * Mirror the agents `/api/narratives` wire contract 1:1 (snake_case) — no mapping layer.
 */

import type { DistributionIntent } from "@/lib/spikes/types";

export interface Narrative {
  id: string;
  author: string;
  seed_text: string;
  intent: DistributionIntent;
  oracle_run_id: string | null;
}

export interface NarrativeCreateInput {
  author?: string | null;
  seed_text: string;
  audience?: string | null;
  angle?: string | null;
}
