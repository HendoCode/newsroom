import { NextResponse } from "next/server";

import { fetchBrainStatus } from "@/lib/agents-client";

/**
 * BFF proxy for the agents `/api/brain/status` endpoint — "which brain am I running" (the
 * voice-kit brain-version indicator). No secrets in the payload: a remote URL and a commit-ish.
 */
export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const status = await fetchBrainStatus();
    return NextResponse.json(status);
  } catch (error) {
    return NextResponse.json(
      { connected: false, error: error instanceof Error ? error.message : "unknown error" },
      { status: 502 },
    );
  }
}
