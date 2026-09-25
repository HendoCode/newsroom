import { NextResponse } from "next/server";

import { AgentsRequestError, finalizePiece } from "@/lib/agents-client";
import { getCurrentUser } from "@/lib/session";

/**
 * BFF route for the finalize/outputs screen's Finalize action (cmw-ui-wireframes screen 10; use
 * case J). Distinct from the generic `/api/pieces/[pieceId]/trigger` route because this is the one
 * trigger whose body carries more than plain attribution — a selectable subset of output formats
 * (D13/Item 5) — so it gets its own BFF route rather than overloading the generic trigger body.
 */
export const dynamic = "force-dynamic";

function isFormatsArray(value: unknown): value is string[] | null {
  if (value === null || value === undefined) return true;
  return Array.isArray(value) && value.every((v) => typeof v === "string");
}

export async function POST(
  request: Request,
  { params }: { params: Promise<{ pieceId: string }> },
) {
  const { pieceId } = await params;
  const user = await getCurrentUser();
  const body: unknown = await request.json().catch(() => ({}));
  const formats = body && typeof body === "object" ? (body as { formats?: unknown }).formats : null;

  if (!isFormatsArray(formats)) {
    return NextResponse.json({ error: "formats must be an array of strings or null" }, { status: 400 });
  }

  try {
    const data = await finalizePiece(pieceId, formats, user?.email);
    return NextResponse.json(data);
  } catch (error) {
    const status = error instanceof AgentsRequestError ? error.status : 502;
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "unknown error" },
      { status },
    );
  }
}
