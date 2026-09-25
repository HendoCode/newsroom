import { NextResponse } from "next/server";

import { AgentsRequestError } from "@/lib/agents-client";

import type { ProjectWorkspaceView } from "@/lib/content-workflow/types";

/**
 * Thin BFF adapter for ContentWorkflow inspect (tracer only).
 * No transition logic or sequencing in TypeScript — delegates to agents.
 */
export const dynamic = "force-dynamic";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ projectId: string }> },
) {
  const { projectId } = await params;
  try {
    const res = await fetch(
      `${process.env.AGENTS_URL}/api/content-workflow/${projectId}/inspect`,
      {
        method: "GET",
        headers: { "content-type": "application/json" },
      },
    );
    const json = await res.json();
    return NextResponse.json(json as ProjectWorkspaceView, { status: res.status });
  } catch (error) {
    const status = error instanceof AgentsRequestError ? error.status : 502;
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "unknown error" },
      { status },
    );
  }
}
