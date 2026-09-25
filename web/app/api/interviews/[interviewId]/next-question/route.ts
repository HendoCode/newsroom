import { NextResponse } from "next/server";

import { AgentsRequestError, requestNextQuestion } from "@/lib/agents-client";

/**
 * BFF route firing the interview engine's next-question sub-step (§5a, Opus) — the "Ask next
 * question" control shown once no question is pending. Forwards 409 (a question already pending,
 * or the persona roster exhausted) so the UI can show its dedicated inline message rather than a
 * generic error.
 */
export const dynamic = "force-dynamic";

export async function POST(
  _request: Request,
  { params }: { params: Promise<{ interviewId: string }> },
) {
  const { interviewId } = await params;
  try {
    const data = await requestNextQuestion(interviewId);
    return NextResponse.json(data);
  } catch (error) {
    const status = error instanceof AgentsRequestError ? error.status : 502;
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "unknown error" },
      { status },
    );
  }
}
