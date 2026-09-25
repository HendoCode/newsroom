import { NextResponse } from "next/server";

import { AgentsRequestError, retireSource, updateSource } from "@/lib/agents-client";

/** BFF routes for editing/retiring one source (Item 6 / D8) — see `../route.ts` for list/create. */
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

export async function PATCH(
  request: Request,
  { params }: { params: Promise<{ sourceId: string }> },
) {
  const { sourceId } = await params;
  const body = await request.json();
  try {
    const updated = await updateSource(sourceId, body);
    return NextResponse.json(updated);
  } catch (error) {
    return errorResponse(error);
  }
}

export async function DELETE(
  _request: Request,
  { params }: { params: Promise<{ sourceId: string }> },
) {
  const { sourceId } = await params;
  try {
    const result = await retireSource(sourceId);
    return NextResponse.json(result);
  } catch (error) {
    return errorResponse(error);
  }
}
