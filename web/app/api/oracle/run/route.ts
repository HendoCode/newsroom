import { NextResponse } from "next/server";

import { AgentsRequestError, runOracle } from "@/lib/agents-client";
import { getCurrentUser } from "@/lib/session";

/**
 * BFF route for the on-demand Oracle run (§1.8, D7; cmw-ui-wireframes screen 8). `triggered_by`
 * is attribution — it becomes the produced spikes' creator — defaulted server-side to the
 * signed-in user, same convention as every other write route here.
 */
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const body = await request.json();
  const user = await getCurrentUser();
  try {
    const result = await runOracle({ triggered_by: user?.email ?? null, ...body });
    return NextResponse.json(result);
  } catch (error) {
    const status = error instanceof AgentsRequestError ? error.status : 502;
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "unknown error" },
      { status },
    );
  }
}
