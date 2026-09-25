import { NextResponse } from "next/server";

import { AgentsRequestError, fetchLessonPreview } from "@/lib/agents-client";

/** BFF route for the Git-diff preview of a proposed lesson (does not write). */
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

export async function GET(
  request: Request,
  { params }: { params: Promise<{ lessonId: string }> },
) {
  const { lessonId } = await params;
  const ruleText = new URL(request.url).searchParams.get("rule_text");
  try {
    const data = await fetchLessonPreview(lessonId, ruleText);
    return NextResponse.json(data);
  } catch (error) {
    return errorResponse(error);
  }
}
