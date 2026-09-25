import { NextResponse } from "next/server";

import { AgentsRequestError, promoteDerivative } from "@/lib/agents-client";
import { getCurrentUser } from "@/lib/session";

/** BFF: promote a child derivative to a top-level Piece. */
export const dynamic = "force-dynamic";

function errorResponse(error: unknown) {
  if (error instanceof AgentsRequestError) {
    return NextResponse.json({ error: error.message }, { status: error.status });
  }
  return NextResponse.json(
    { error: error instanceof Error ? error.message : "unknown error" },
    { status: 502 },
  );
}

export async function POST(
  request: Request,
  { params }: { params: Promise<{ pieceId: string; artifactId: string }> },
) {
  const { pieceId, artifactId } = await params;
  const body = (await request.json().catch(() => ({}))) as { owner?: string };
  const user = await getCurrentUser();
  try {
    const data = await promoteDerivative(pieceId, artifactId, {
      owner: body.owner ?? user?.email ?? null,
      actor: user?.email ?? null,
    });
    return NextResponse.json(data);
  } catch (error) {
    return errorResponse(error);
  }
}
