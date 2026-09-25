import { NextResponse } from "next/server";

import { AgentsRequestError, rollbackVoiceFile } from "@/lib/agents-client";
import { getCurrentUser } from "@/lib/session";
import type { VoiceFileKey } from "@/lib/voice-kit/types";

/** BFF route for rolling a voice-pack file back to an earlier Git revision (screen 11). */
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
  { params }: { params: Promise<{ slug: string; fileKey: string }> },
) {
  const { slug, fileKey } = await params;
  const body = await request.json();
  const user = await getCurrentUser();
  try {
    const commit = await rollbackVoiceFile(slug, fileKey as VoiceFileKey, {
      actor: user?.email ?? null,
      actor_name: user?.name ?? null,
      ...body,
    });
    return NextResponse.json(commit);
  } catch (error) {
    return errorResponse(error);
  }
}
