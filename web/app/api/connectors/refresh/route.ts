import { NextResponse } from "next/server";

import { AgentsRequestError, refreshSources } from "@/lib/agents-client";

/**
 * BFF route for the on-demand "Refresh sources now" action (D7 — no scheduler). Proxies straight
 * to the connectors' refresh entrypoint (`agents/app/connectors/refresh.py`) — never reimplemented
 * here. A per-source failure is reported inline in the response, not an HTTP error (warns, does
 * not block, §5), so this route only maps transport-level failures.
 */
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const body = await request.json().catch(() => ({}));
  try {
    const result = await refreshSources(body);
    return NextResponse.json(result);
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
