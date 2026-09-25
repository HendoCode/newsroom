import { NextResponse } from "next/server";

import { AgentsRequestError, fetchVoicePack } from "@/lib/agents-client";

/** BFF route for one voice pack's current content (screen 11) — see `../route.ts` for the list. */
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

export async function GET(_request: Request, { params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  try {
    const data = await fetchVoicePack(slug);
    return NextResponse.json(data);
  } catch (error) {
    return errorResponse(error);
  }
}
