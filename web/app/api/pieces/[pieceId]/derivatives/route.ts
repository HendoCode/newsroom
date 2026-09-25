import { NextResponse } from "next/server";

import { AgentsRequestError, createDerivative, fetchDerivatives } from "@/lib/agents-client";

/** BFF for derivative child artifacts of an anchor piece (cmw-lesson-lineage-impl). */
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

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ pieceId: string }> },
) {
  const { pieceId } = await params;
  try {
    const data = await fetchDerivatives(pieceId);
    return NextResponse.json(data);
  } catch (error) {
    return errorResponse(error);
  }
}

export async function POST(
  request: Request,
  { params }: { params: Promise<{ pieceId: string }> },
) {
  const { pieceId } = await params;
  const body = (await request.json().catch(() => ({}))) as {
    destination?: string;
    title?: string;
  };
  if (!body.destination) {
    return NextResponse.json({ error: "destination is required" }, { status: 422 });
  }
  try {
    const data = await createDerivative(pieceId, {
      destination: body.destination,
      title: body.title ?? null,
    });
    return NextResponse.json(data, { status: 201 });
  } catch (error) {
    return errorResponse(error);
  }
}
