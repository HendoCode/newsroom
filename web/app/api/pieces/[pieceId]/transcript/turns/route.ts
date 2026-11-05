import { NextResponse } from "next/server";

import { AgentsRequestError, fetchTranscriptTurns } from "@/lib/agents-client";

/**
 * BFF route for the sacred, piece-scoped transcript (D16b) — structured turns for the interview
 * surface's "review & edit my answers" panel, sibling to `/api/pieces/[pieceId]/trigger`.
 */
export const dynamic = "force-dynamic";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ pieceId: string }> },
) {
  const { pieceId } = await params;
  try {
    const data = await fetchTranscriptTurns(pieceId);
    return NextResponse.json(data);
  } catch (error) {
    const status = error instanceof AgentsRequestError ? error.status : 502;
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "unknown error" },
      { status },
    );
  }
}
