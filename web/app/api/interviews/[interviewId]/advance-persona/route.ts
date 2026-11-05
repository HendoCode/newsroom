import { NextResponse } from "next/server";

import { advancePersona, AgentsRequestError } from "@/lib/agents-client";

/**
 * BFF route for skip/go-back roster navigation — deliberately separate from `respond/route.ts`:
 * this is pure index arithmetic with no classifier call and no pending-question gate, so a human
 * can move past a persona without being forced to generate (and ignore) a question first.
 */
export const dynamic = "force-dynamic";

export async function POST(
  request: Request,
  { params }: { params: Promise<{ interviewId: string }> },
) {
  const { interviewId } = await params;
  const body: unknown = await request.json().catch(() => null);
  const direction =
    body && typeof body === "object" ? (body as { direction?: unknown }).direction : null;
  if (direction !== "skip" && direction !== "go-back") {
    return NextResponse.json(
      { error: 'direction must be "skip" or "go-back"' },
      { status: 400 },
    );
  }

  try {
    const data = await advancePersona(interviewId, direction);
    return NextResponse.json(data);
  } catch (error) {
    const status = error instanceof AgentsRequestError ? error.status : 502;
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "unknown error" },
      { status },
    );
  }
}
