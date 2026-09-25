import { NextResponse } from "next/server";

import { AgentsRequestError, fetchSpikes } from "@/lib/agents-client";

/**
 * BFF route for the Spikes & Vault browser (§1.6/§1.7, D15; cmw-ui-wireframes screen 5). Proxies
 * straight to the agents data layer — `web/` holds no work-state and runs no orchestration (D5).
 * The D15 filters/sort are applied client-side over this full list (`lib/spikes/filters.ts`),
 * mirroring the dashboard's `FilterBar` discipline.
 */
export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const data = await fetchSpikes();
    return NextResponse.json(data);
  } catch (error) {
    const status = error instanceof AgentsRequestError ? error.status : 502;
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "unknown error" },
      { status },
    );
  }
}
