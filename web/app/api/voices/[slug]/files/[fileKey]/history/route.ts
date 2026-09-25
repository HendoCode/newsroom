import { NextResponse } from "next/server";

import { AgentsRequestError, fetchVoiceFileHistory } from "@/lib/agents-client";
import type { VoiceFileKey } from "@/lib/voice-kit/types";

/** BFF route for a voice-pack file's Git version history (screen 11). */
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
  { params }: { params: Promise<{ slug: string; fileKey: string }> },
) {
  const { slug, fileKey } = await params;
  try {
    const data = await fetchVoiceFileHistory(slug, fileKey as VoiceFileKey);
    return NextResponse.json(data);
  } catch (error) {
    return errorResponse(error);
  }
}
