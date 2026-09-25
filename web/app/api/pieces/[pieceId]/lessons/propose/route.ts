import { NextResponse } from "next/server";

import { AgentsRequestError, proposeLessons } from "@/lib/agents-client";
import { getCurrentUser } from "@/lib/session";

/**
 * BFF route for the lessons loop's missing first step (D12; domain model §1.18): diffs the
 * machine's final draft against the pasted "what was actually published" text and proposes
 * per-voice lessons (Opus). Gets its own route rather than the generic
 * `/api/pieces/[pieceId]/trigger` route because it carries a real body (`published_content`) and
 * isn't an orchestration-state trigger at all — proposing doesn't move the piece's stage. Mirrors
 * the finalize/review-mint BFF routes' validate-then-proxy-then-pass-through-status shape.
 */
export const dynamic = "force-dynamic";

export async function POST(
  request: Request,
  { params }: { params: Promise<{ pieceId: string }> },
) {
  const { pieceId } = await params;
  const user = await getCurrentUser();
  const body: unknown = await request.json().catch(() => ({}));
  const publishedContent =
    body && typeof body === "object" ? (body as { published_content?: unknown }).published_content : null;

  if (typeof publishedContent !== "string" || !publishedContent.trim()) {
    return NextResponse.json({ error: "published_content is required" }, { status: 400 });
  }

  try {
    const data = await proposeLessons(pieceId, {
      published_content: publishedContent,
      actor: user?.email ?? null,
    });
    return NextResponse.json(data);
  } catch (error) {
    const status = error instanceof AgentsRequestError ? error.status : 502;
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "unknown error" },
      { status },
    );
  }
}
