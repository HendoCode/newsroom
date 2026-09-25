import { NextResponse } from "next/server";

import { AgentsRequestError, markInterviewComplete } from "@/lib/agents-client";

/**
 * BFF route for "Mark interview complete" — a SIGNAL, never the draft trigger (D16a). It flips
 * `Interview.status` only; a piece owner still has to press "enough input" separately
 * (`/api/pieces/[pieceId]/trigger`) to advance the piece to drafting.
 */
export const dynamic = "force-dynamic";

export async function POST(
  _request: Request,
  { params }: { params: Promise<{ interviewId: string }> },
) {
  const { interviewId } = await params;
  try {
    const data = await markInterviewComplete(interviewId);
    return NextResponse.json(data);
  } catch (error) {
    const status = error instanceof AgentsRequestError ? error.status : 502;
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "unknown error" },
      { status },
    );
  }
}
