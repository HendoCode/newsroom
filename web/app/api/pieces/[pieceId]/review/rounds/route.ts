import { NextResponse } from "next/server";

import { AgentsRequestError, fetchReviewRounds } from "@/lib/agents-client";

/**
 * BFF route: list every review round for a piece (cmw-review-round-ux-impl). The round is the
 * primary REST resource — the Doc is a child link inside each round. Read-only proxy; no body
 * validation needed.
 */
export const dynamic = "force-dynamic";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ pieceId: string }> },
) {
  const { pieceId } = await params;
  try {
    const data = await fetchReviewRounds(pieceId);
    return NextResponse.json(data);
  } catch (error) {
    const status = error instanceof AgentsRequestError ? error.status : 502;
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "unknown error" },
      { status },
    );
  }
}