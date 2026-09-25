import { NextResponse } from "next/server";

import { AgentsRequestError, fetchPendingLessons } from "@/lib/agents-client";

/** BFF route for the proposed-lessons gate (D12; domain model §1.18) — pending proposals,
 * optionally narrowed to one voice for the voice-kit screen. */
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

export async function GET(request: Request) {
  const voice = new URL(request.url).searchParams.get("voice");
  try {
    const data = await fetchPendingLessons(voice);
    return NextResponse.json(data);
  } catch (error) {
    return errorResponse(error);
  }
}
