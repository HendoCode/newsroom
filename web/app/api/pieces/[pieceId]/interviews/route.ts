import { NextResponse } from "next/server";

import { AgentsRequestError, openInterview } from "@/lib/agents-client";

/**
 * BFF route opening an Interview session on a piece (D5-context-assembly §5) — kickoff steps 3-5
 * (cmw-ui-wireframes screen 6): assign the expert, hand it the agent's pre-selected interviewer
 * personas, and hand back the interview id the kickoff screen turns into a shareable
 * `/interviews/{id}` link. The interview-taking surface itself is a separate, later ticket.
 */
export const dynamic = "force-dynamic";

export async function POST(
  request: Request,
  { params }: { params: Promise<{ pieceId: string }> },
) {
  const { pieceId } = await params;
  const body = await request.json();
  try {
    const interview = await openInterview(pieceId, body);
    return NextResponse.json(interview);
  } catch (error) {
    const status = error instanceof AgentsRequestError ? error.status : 502;
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "unknown error" },
      { status },
    );
  }
}
