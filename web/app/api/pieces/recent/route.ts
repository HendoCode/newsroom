import { NextResponse } from "next/server";

import { fetchRecentPieces } from "@/lib/agents-client";

/**
 * BFF route for the Operator Desk's recent-pieces strip (`web/app/content-machine/`).
 *
 * Same posture as the `/api/dashboard` proxy: `web/` holds no work-state (D5), so this reads the
 * agents projection over REST and degrades to a 502 the desk renders as a quiet "unavailable"
 * note. The agents side returns an honest empty list when Mongo is unconfigured — there is
 * deliberately no seed/hardcoded fallback anywhere on this path.
 */
export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const data = await fetchRecentPieces();
    return NextResponse.json(data);
  } catch (error) {
    return NextResponse.json(
      { reachable: false, error: error instanceof Error ? error.message : "unknown error" },
      { status: 502 },
    );
  }
}
