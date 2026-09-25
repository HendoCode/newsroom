import { NextResponse } from "next/server";

import { AgentsRequestError, editTranscriptAnswer } from "@/lib/agents-client";

/**
 * BFF route for the interviewee's own edit of a previously stored answer (D16b) — splices the new
 * text into that turn in place; the question, every other turn, and the rest of the transcript are
 * untouched. Requires `interview_id` (the surface the edit is being made from) so the agents side
 * can refuse the write once that interview is complete — the transcript then becomes read-only.
 */
export const dynamic = "force-dynamic";

export async function POST(
  request: Request,
  { params }: { params: Promise<{ pieceId: string; turnId: string }> },
) {
  const { pieceId, turnId } = await params;
  const body: unknown = await request.json().catch(() => null);
  const text = body && typeof body === "object" ? (body as { text?: unknown }).text : null;
  if (typeof text !== "string" || text.trim().length === 0) {
    return NextResponse.json({ error: "text is required" }, { status: 400 });
  }
  const interviewId =
    body && typeof body === "object" ? (body as { interview_id?: unknown }).interview_id : null;
  if (typeof interviewId !== "string" || interviewId.trim().length === 0) {
    return NextResponse.json({ error: "interview_id is required" }, { status: 400 });
  }

  try {
    const data = await editTranscriptAnswer(pieceId, turnId, interviewId, text);
    return NextResponse.json(data);
  } catch (error) {
    const status = error instanceof AgentsRequestError ? error.status : 502;
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "unknown error" },
      { status },
    );
  }
}
