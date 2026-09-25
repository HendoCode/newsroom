import { NextResponse } from "next/server";

import { AgentsRequestError, mintReviewRound } from "@/lib/agents-client";

/**
 * BFF route for the review-round screen's Mint action (cmw-ui-wireframes screen 04; D4/D11). Gets
 * its own route rather than the generic `/api/pieces/[pieceId]/trigger` route because it carries a
 * real body (`share_mode` + `reviewer_emails`) and isn't an orchestration-state trigger at all — it
 * mints a Doc without moving the piece's stage. Mirrors the finalize BFF route's validate-then-
 * proxy-then-pass-through-status shape.
 */
export const dynamic = "force-dynamic";

const SHARE_MODES = new Set(["internal", "external"]);

function isReviewerEmails(value: unknown): value is string[] | null {
  if (value === null || value === undefined) return true;
  return Array.isArray(value) && value.every((v) => typeof v === "string");
}

export async function POST(
  request: Request,
  { params }: { params: Promise<{ pieceId: string }> },
) {
  const { pieceId } = await params;
  const body: unknown = await request.json().catch(() => ({}));
  const shareMode =
    body && typeof body === "object" ? (body as { share_mode?: unknown }).share_mode : "internal";
  const reviewerEmails =
    body && typeof body === "object" ? (body as { reviewer_emails?: unknown }).reviewer_emails : null;

  if (typeof shareMode !== "string" || !SHARE_MODES.has(shareMode)) {
    return NextResponse.json({ error: "share_mode must be \"internal\" or \"external\"" }, { status: 400 });
  }
  if (!isReviewerEmails(reviewerEmails)) {
    return NextResponse.json({ error: "reviewer_emails must be an array of strings or null" }, { status: 400 });
  }

  try {
    const data = await mintReviewRound(pieceId, {
      share_mode: shareMode as "internal" | "external",
      reviewer_emails: reviewerEmails,
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
