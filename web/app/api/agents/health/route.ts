import { NextResponse } from "next/server";

import { fetchAgentsHealth } from "@/lib/agents-client";

/**
 * BFF proxy that calls the Python `agents/` service `/health` over REST (docs/design.md §6).
 * Proves the web/ ↔ agents/ wiring end-to-end. The browser talks only to this same-origin
 * route; the agents URL and any credentials stay server-side.
 */
export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const health = await fetchAgentsHealth();
    return NextResponse.json({ reachable: true, agents: health });
  } catch (error) {
    return NextResponse.json(
      { reachable: false, error: error instanceof Error ? error.message : "unknown error" },
      { status: 502 },
    );
  }
}
