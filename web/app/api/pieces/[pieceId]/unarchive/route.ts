import { NextResponse } from "next/server";

import { AgentsRequestError, unarchivePiece } from "@/lib/agents-client";

/** BFF route for restoring an archived piece to the dashboard queue — see `.../archive/route.ts`. */
export const dynamic = "force-dynamic";

export async function POST(
  _request: Request,
  { params }: { params: Promise<{ pieceId: string }> },
) {
  const { pieceId } = await params;
  try {
    const data = await unarchivePiece(pieceId);
    return NextResponse.json(data);
  } catch (error) {
    const status = error instanceof AgentsRequestError ? error.status : 502;
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "unknown error" },
      { status },
    );
  }
}
