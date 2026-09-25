import { NextResponse } from "next/server";

import { AgentsRequestError, mintSpikeFromNarrative } from "@/lib/agents-client";
import { getCurrentUser } from "@/lib/session";

/**
 * BFF route for the "new piece from my own idea" fast path (cmw-narrative-first-entry-point):
 * mint a Spike straight from a Narrative, no Oracle ranking run. `creator` is attribution,
 * defaulted server-side to the signed-in user — same convention as `/api/narratives`'s `author`
 * and `/api/spikes/{id}/pick`'s `owner`.
 */
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const body = await request.json();
  const user = await getCurrentUser();
  try {
    const created = await mintSpikeFromNarrative({ creator: user?.email ?? null, ...body });
    return NextResponse.json(created, { status: 201 });
  } catch (error) {
    const status = error instanceof AgentsRequestError ? error.status : 502;
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "unknown error" },
      { status },
    );
  }
}
