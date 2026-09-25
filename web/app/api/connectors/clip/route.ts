import { NextResponse } from "next/server";

import { AgentsRequestError, clipIn } from "@/lib/agents-client";

/**
 * BFF route for the credential-free LinkedIn/X clip-in (D8). Proxies straight to
 * `agents/app/connectors/clipin.py` — pasted text/URL + minimal metadata, no fetch, no auth.
 */
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const body = await request.json();
  try {
    const result = await clipIn(body);
    return NextResponse.json(result, { status: 201 });
  } catch (error) {
    if (error instanceof AgentsRequestError) {
      return NextResponse.json({ error: error.message }, { status: error.status });
    }
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "unknown error" },
      { status: 502 },
    );
  }
}
