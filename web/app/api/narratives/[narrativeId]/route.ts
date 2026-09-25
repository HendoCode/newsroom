import { NextResponse } from "next/server";

import { AgentsRequestError, fetchNarrative } from "@/lib/agents-client";

/** BFF route for one Narrative — the only way a human can see their spoken narrative's full
 * `seed_text` again once the Radar page it was typed on has moved on (cmw-first-run-ux-batch
 * item 6). Mirrors `app/api/spikes/[spikeId]/route.ts`. */
export const dynamic = "force-dynamic";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ narrativeId: string }> },
) {
  const { narrativeId } = await params;
  try {
    const data = await fetchNarrative(narrativeId);
    return NextResponse.json(data);
  } catch (error) {
    const status = error instanceof AgentsRequestError ? error.status : 502;
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "unknown error" },
      { status },
    );
  }
}
