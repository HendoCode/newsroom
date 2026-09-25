import { NextResponse } from "next/server";

import { AgentsRequestError, pickSpike } from "@/lib/agents-client";
import { getCurrentUser } from "@/lib/session";

/**
 * BFF route for the pick -> create-piece hand-off (use case C; cmw-ui-wireframes screen 6 steps
 * 1-2). `owner` is attribution, not a permission field (§1.17) — defaults to the signed-in user
 * server-side when the client didn't set one, same convention as the source registry's `POST`.
 */
export const dynamic = "force-dynamic";

export async function POST(
  request: Request,
  { params }: { params: Promise<{ spikeId: string }> },
) {
  const { spikeId } = await params;
  const body = await request.json();
  const user = await getCurrentUser();
  try {
    const result = await pickSpike(spikeId, { owner: user?.email ?? null, ...body });
    return NextResponse.json(result, { status: 201 });
  } catch (error) {
    const status = error instanceof AgentsRequestError ? error.status : 502;
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "unknown error" },
      { status },
    );
  }
}
