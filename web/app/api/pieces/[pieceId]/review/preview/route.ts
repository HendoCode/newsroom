import { NextResponse } from "next/server";

import { AgentsRequestError, fetchReviewPreview } from "@/lib/agents-client";

/**
 * BFF route for the review-round screen's assisted "reviews done" preview (open-decisions Item 7)
 * — "N comments · M edits — fold these in?" read-only over the piece's currently open round. A
 * 404 here (no piece / no open round) is a client-visible outcome the screen renders inline, not a
 * bug — same pass-through-status convention as every other proxy route in this file's siblings.
 */
export const dynamic = "force-dynamic";

export async function GET(_request: Request, { params }: { params: Promise<{ pieceId: string }> }) {
  const { pieceId } = await params;
  try {
    const data = await fetchReviewPreview(pieceId);
    return NextResponse.json(data);
  } catch (error) {
    const status = error instanceof AgentsRequestError ? error.status : 502;
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "unknown error" },
      { status },
    );
  }
}
