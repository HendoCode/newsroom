import { NextResponse } from "next/server";

import { AgentsRequestError, archivePiece } from "@/lib/agents-client";

/**
 * BFF route for hiding a piece from the dashboard queue (triage at scale). Distinct from the
 * generic `/api/pieces/[pieceId]/trigger` route because archive is not a state-machine edge — it
 * works regardless of the piece's current stage, mirroring `.../finalize`'s own-dedicated-route
 * shape rather than the generic trigger.
 */
export const dynamic = "force-dynamic";

export async function POST(
  _request: Request,
  { params }: { params: Promise<{ pieceId: string }> },
) {
  const { pieceId } = await params;
  try {
    const data = await archivePiece(pieceId);
    return NextResponse.json(data);
  } catch (error) {
    const status = error instanceof AgentsRequestError ? error.status : 502;
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "unknown error" },
      { status },
    );
  }
}
