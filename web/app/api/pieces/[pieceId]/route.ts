import { NextResponse } from "next/server";

import { AgentsRequestError, fetchPieceDetail } from "@/lib/agents-client";
import { getCurrentUser } from "@/lib/session";

/**
 * BFF route for the piece-detail screen (cmw-ui-wireframes screen 2; Item 2).
 *
 * Same shape as `/api/dashboard`: `web/` holds no work-state and runs no orchestration (D5), so
 * this just reads the agents data layer over REST. Unlike the dashboard proxy, the underlying
 * status is forwarded (not collapsed to 502) so a genuine 404 renders the page's not-found state
 * rather than a generic error banner.
 */
export const dynamic = "force-dynamic";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ pieceId: string }> },
) {
  const { pieceId } = await params;
  const user = await getCurrentUser();
  try {
    const data = await fetchPieceDetail(pieceId, user?.email);
    return NextResponse.json(data);
  } catch (error) {
    const status = error instanceof AgentsRequestError ? error.status : 502;
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "unknown error" },
      { status },
    );
  }
}
