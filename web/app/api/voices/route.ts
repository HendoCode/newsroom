import { NextResponse } from "next/server";

import { AgentsRequestError, fetchVoices } from "@/lib/agents-client";

/** BFF route for the voice selector (screen 11 / D12) — proxies straight to the agents data
 * layer, same pattern as `/api/sources`. */
export const dynamic = "force-dynamic";

function errorResponse(error: unknown) {
  if (error instanceof AgentsRequestError) {
    return NextResponse.json({ error: error.message }, { status: error.status });
  }
  return NextResponse.json(
    { error: error instanceof Error ? error.message : "unknown error" },
    { status: 502 },
  );
}

export async function GET() {
  try {
    const data = await fetchVoices();
    return NextResponse.json(data);
  } catch (error) {
    return errorResponse(error);
  }
}
