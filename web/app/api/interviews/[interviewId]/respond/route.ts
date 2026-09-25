import { NextResponse } from "next/server";

import { AgentsRequestError, respondToInterview } from "@/lib/agents-client";

/**
 * BFF route for the composer's free-form submission — classifies (Sonnet, D6) and routes into the
 * bounded op set (answer / research-this / meta-command / tangent). The whole point of this route
 * is that `web/` never guesses the op itself; it always round-trips through the real classifier.
 */
export const dynamic = "force-dynamic";

export async function POST(
  request: Request,
  { params }: { params: Promise<{ interviewId: string }> },
) {
  const { interviewId } = await params;
  const body: unknown = await request.json().catch(() => null);
  const text = body && typeof body === "object" ? (body as { text?: unknown }).text : null;
  if (typeof text !== "string" || text.trim().length === 0) {
    return NextResponse.json({ error: "text is required" }, { status: 400 });
  }

  try {
    const data = await respondToInterview(interviewId, text);
    return NextResponse.json(data);
  } catch (error) {
    const status = error instanceof AgentsRequestError ? error.status : 502;
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "unknown error" },
      { status },
    );
  }
}
