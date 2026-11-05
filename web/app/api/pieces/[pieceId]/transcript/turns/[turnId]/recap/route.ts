import { NextResponse } from "next/server";

import { AgentsRequestError, recapTranscriptTurn } from "@/lib/agents-client";

/**
 * BFF route regenerating the "here's what I heard" confirmation view over an already-stored (and
 * possibly just-edited) turn — read-only; never writes back over the transcript answer (D16b).
 */
export const dynamic = "force-dynamic";

export async function POST(
  _request: Request,
  { params }: { params: Promise<{ pieceId: string; turnId: string }> },
) {
  const { pieceId, turnId } = await params;
  try {
    const data = await recapTranscriptTurn(pieceId, turnId);
    return NextResponse.json(data);
  } catch (error) {
    const status = error instanceof AgentsRequestError ? error.status : 502;
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "unknown error" },
      { status },
    );
  }
}
