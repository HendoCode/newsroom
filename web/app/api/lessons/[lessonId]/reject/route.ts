import { NextResponse } from "next/server";

import { AgentsRequestError, rejectLesson } from "@/lib/agents-client";
import { getCurrentUser } from "@/lib/session";

/** BFF route for the D12 reject gate. Never touches Git. */
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
    const lesson = await rejectLesson(lessonId, { actor: user?.email ?? null, ...body });
    return NextResponse.json(lesson);
  } catch (error) {
    return errorResponse(error);
  }
}
