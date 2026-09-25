import { NextResponse } from "next/server";

import { AgentsRequestError } from "@/lib/agents-client";

/**
 * Thin BFF adapter for ContentWorkflow submit (tracer only).
 * No transition logic or sequencing in TypeScript — delegates to agents.
 */
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const body = await request.json();
  try {
    const res = await fetch(`${process.env.AGENTS_URL}/api/content-workflow/submit`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    });
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
