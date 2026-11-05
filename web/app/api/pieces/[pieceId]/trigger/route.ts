import { NextResponse } from "next/server";

import { AgentsRequestError, triggerPiece, type PieceTrigger } from "@/lib/agents-client";
import { getCurrentUser } from "@/lib/session";

/**
 * BFF route firing a stage-contextual orchestration trigger (the state machine, D5) — the
 * deliberate "enough input" → draft button (D16a) and the review/finalize/lessons/pause triggers
 * the piece-detail "Next action" card renders. Flat auth: the signed-in user is forwarded only as
 * attribution (`actor`), never a permission check (§1.17) — anyone signed in can fire any legal
 * trigger; the agents state machine is what rejects an illegal stage (409).
 */
export const dynamic = "force-dynamic";

// Exactly the trigger set `agents/app/orchestration/routes.py` exposes. Whitelisted server-side so
// a malformed client payload can't reach the agents service with an arbitrary path segment.
const ALLOWED_TRIGGERS = new Set<PieceTrigger>([
  "enough-input",
  "reviews-done",
  "finalize",
  "capture-lessons",
  "finish-lessons",
  "route-to-interview",
  "pause",
  "resume",
  "publish",
]);

function isPieceTrigger(value: unknown): value is PieceTrigger {
  return typeof value === "string" && ALLOWED_TRIGGERS.has(value as PieceTrigger);
}

export async function POST(
  request: Request,
  { params }: { params: Promise<{ pieceId: string }> },
) {
  const { pieceId } = await params;
  const user = await getCurrentUser();
  const body: unknown = await request.json().catch(() => null);
  const trigger = body && typeof body === "object" ? (body as { trigger?: unknown }).trigger : null;

  if (!isPieceTrigger(trigger)) {
    return NextResponse.json({ error: `unknown trigger ${String(trigger)}` }, { status: 400 });
  }

  try {
    const data = await triggerPiece(pieceId, trigger, user?.email);
    return NextResponse.json(data);
  } catch (error) {
    const status = error instanceof AgentsRequestError ? error.status : 502;
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "unknown error" },
      { status },
    );
  }
}
