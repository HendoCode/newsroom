import { NextResponse } from "next/server";

import { AgentsRequestError, fetchSpike } from "@/lib/agents-client";

/** BFF route for one spike — the kickoff screen's starting point (screen 6 step 1). */
export const dynamic = "force-dynamic";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ spikeId: string }> },
) {
  const { spikeId } = await params;
  try {
    const data = await fetchSpike(spikeId);
    return NextResponse.json(data);
  } catch (error) {
    const status = error instanceof AgentsRequestError ? error.status : 502;
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "unknown error" },
      { status },
    );
  }
}
