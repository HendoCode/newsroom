import { NextResponse } from "next/server";

import { AgentsRequestError, fetchInterview } from "@/lib/agents-client";

/**
 * BFF route for the interview surface (cmw-ui-wireframes screen 3) — reads one Interview's
 * turn-taking state. Same forward-the-real-status convention as `/api/pieces/[pieceId]` (a genuine
 * 404 should render the page's not-found state, not a generic error banner).
 */
export const dynamic = "force-dynamic";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ interviewId: string }> },
) {
  const { interviewId } = await params;
  try {
    const data = await fetchInterview(interviewId);
    return NextResponse.json(data);
  } catch (error) {
    const status = error instanceof AgentsRequestError ? error.status : 502;
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "unknown error" },
      { status },
    );
  }
}
