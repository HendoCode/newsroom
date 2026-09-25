import { NextResponse } from "next/server";

import { AgentsRequestError, updateVoiceFile } from "@/lib/agents-client";
import { getCurrentUser } from "@/lib/session";
import type { VoiceFileKey } from "@/lib/voice-kit/types";

/** BFF route for editing/committing one voice-pack file (screen 11 / D12). */
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

export async function PUT(
  request: Request,
  { params }: { params: Promise<{ slug: string; fileKey: string }> },
) {
  const { slug, fileKey } = await params;
  const body = await request.json();
  // `actor`/`actor_name` attribute the Git commit to the signed-in user (D15/§1.17) — attribution
  // only, never a permission check (D12: any employee may edit any kit).
  const user = await getCurrentUser();
  try {
    const commit = await updateVoiceFile(slug, fileKey as VoiceFileKey, {
      actor: user?.email ?? null,
      actor_name: user?.name ?? null,
      ...body,
    });
    return NextResponse.json(commit);
  } catch (error) {
    return errorResponse(error);
  }
}
