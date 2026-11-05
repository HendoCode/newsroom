import { NextResponse } from "next/server";

import { fetchDashboard } from "@/lib/agents-client";
import { getCurrentUser } from "@/lib/session";

/**
 * BFF route for the dashboard's shared work queue (docs/design.md §3, §6; Item 3).
 *
 * The `web/` service is UI + BFF only — it holds no work-state and runs no orchestration (D5). This
 * handler reads the queue from the `agents/` data layer over REST, forwarding the signed-in user's
 * email so the agents service can attribute placeholder SEED cards to the viewer. The email is
 * server-derived from the session (middleware already gated this route); it is NOT a permission
 * filter — authorization is flat (§1.17), so the full queue is returned and the "needs my action"
 * predicate is computed client-side.
 */
export const dynamic = "force-dynamic";

export async function GET() {
  const user = await getCurrentUser();
  try {
    const data = await fetchDashboard(user?.email);
    return NextResponse.json(data);
  } catch (error) {
    return NextResponse.json(
      { reachable: false, error: error instanceof Error ? error.message : "unknown error" },
      { status: 502 },
    );
  }
}
