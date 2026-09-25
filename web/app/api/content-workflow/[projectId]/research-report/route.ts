import { NextResponse } from "next/server";

import { AgentsRequestError } from "@/lib/agents-client";

/**
 * Thin BFF adapter for the project's research-report artifact (research-v1): GET returns the
 * research gate (required / satisfied / by what), POST records a new report. No transition
 * logic in TypeScript — delegates to agents.
 */
export const dynamic = "force-dynamic";

async function proxy(method: "GET" | "POST", projectId: string, body?: unknown) {
  try {
    const res = await fetch(
      `${process.env.AGENTS_URL}/api/content-workflow/${projectId}/research-report`,
      {
        method,
        headers: { "content-type": "application/json" },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      },
    );
    const json = await res.json();
    return NextResponse.json(json, { status: res.status });
  } catch (error) {
    const status = error instanceof AgentsRequestError ? error.status : 502;
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "unknown error" },
      { status },
    );
  }
}

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ projectId: string }> },
) {
  const { projectId } = await params;
  return proxy("GET", projectId);
}

export async function POST(
  request: Request,
  { params }: { params: Promise<{ projectId: string }> },
) {
  const { projectId } = await params;
  const body = await request.json();
  return proxy("POST", projectId, body);
}
