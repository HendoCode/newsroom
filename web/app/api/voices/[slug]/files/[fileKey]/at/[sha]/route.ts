import { NextResponse } from "next/server";

import { AgentsRequestError, fetchVoiceFileAt } from "@/lib/agents-client";
import type { VoiceFileKey } from "@/lib/voice-kit/types";

/** BFF route for a voice-pack file's content as of a past commit (screen 11 diff/rollback preview). */
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
  { params }: { params: Promise<{ slug: string; fileKey: string; sha: string }> },
) {
  const { slug, fileKey, sha } = await params;
  try {
    const data = await fetchVoiceFileAt(slug, fileKey as VoiceFileKey, sha);
    return NextResponse.json(data);
  } catch (error) {
    return errorResponse(error);
  }
}
