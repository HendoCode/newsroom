import { NextResponse } from "next/server";

import { AgentsRequestError, decideLessonsBatch } from "@/lib/agents-client";
import { getCurrentUser } from "@/lib/session";

/** BFF route for voice-kit batch accept/reject (cmw-lesson-lineage-impl). */
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

export async function POST(request: Request) {
  const body = (await request.json().catch(() => ({}))) as {
    action?: "accept" | "reject";
    lesson_ids?: string[];
    rule_texts?: Record<string, string>;
  };
  if (body.action !== "accept" && body.action !== "reject") {
    return NextResponse.json({ error: "action must be accept or reject" }, { status: 422 });
  }
  if (!Array.isArray(body.lesson_ids) || body.lesson_ids.length === 0) {
    return NextResponse.json({ error: "lesson_ids is required" }, { status: 422 });
  }
  const user = await getCurrentUser();
  try {
    const data = await decideLessonsBatch(body.action, body.lesson_ids, {
      actor: user?.email ?? null,
      rule_texts: body.rule_texts,
    });
    return NextResponse.json(data);
  } catch (error) {
    return errorResponse(error);
  }
}
