import { NextResponse } from "next/server";

import { AgentsRequestError, updatePieceTitle } from "@/lib/agents-client";

/**
 * BFF route for updating a piece's title (dashboard rename).
 */
export const dynamic = "force-dynamic";

export async function POST(
  request: Request,
  { params }: { params: Promise<{ pieceId: string }> },
) {
  const { pieceId } = await params;
  try {
    const { title } = await request.json();
    const data = await updatePieceTitle(pieceId, title);
    return NextResponse.json(data);
  } catch (error) {
    const status = error instanceof AgentsRequestError ? error.status : 502;
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "unknown error" },
      { status },
    );
  }
}