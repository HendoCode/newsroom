import { NextResponse } from "next/server";

import { acceptLesson, AgentsRequestError } from "@/lib/agents-client";
import { getCurrentUser } from "@/lib/session";

/** BFF route for the D12 accept gate: "accept/edit in one click" — `rule_text` set means edited,
 * unset means accept-as-proposed. Commits the accepted rule to Git via the lessons loop. */
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

export async function POST(
  request: Request,
  { params }: { params: Promise<{ lessonId: string }> },
) {
  const { lessonId } = await params;
  const body = await request.json().catch(() => ({}));
  const user = await getCurrentUser();
  try {
    const lesson = await acceptLesson(lessonId, { actor: user?.email ?? null, ...body });
    return NextResponse.json(lesson);
  } catch (error) {
    return errorResponse(error);
  }
}
