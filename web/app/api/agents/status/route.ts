import { NextResponse } from "next/server";

import { fetchAgentsStatus } from "@/lib/agents-client";

/**
 * BFF proxy for the agents `/api/status` stub — surfaces the downstream seams (orchestration,
 * pipeline stages, LLM readiness) to the UI without exposing the agents URL or any secrets.
 */
export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const status = await fetchAgentsStatus();
    return NextResponse.json({ reachable: true, ...status });
  } catch (error) {
    return NextResponse.json(
      { reachable: false, error: error instanceof Error ? error.message : "unknown error" },
      { status: 502 },
    );
  }
}
