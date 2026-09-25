import { NextResponse } from "next/server";

import { AgentsRequestError, createSource, fetchSources } from "@/lib/agents-client";
import { getCurrentUser } from "@/lib/session";

/**
 * BFF routes for the source registry (Item 6 / D8; cmw-ui-wireframes screen 7).
 *
 * `web/` holds no work-state and runs no orchestration (D5) — both handlers proxy straight to the
 * `agents/` data layer over REST. A non-2xx from agents (400 invariant violation, 503 unconfigured)
 * passes through with its real status rather than collapsing to an opaque 502.
 */
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

export async function GET() {
  try {
    const data = await fetchSources();
    return NextResponse.json(data);
  } catch (error) {
    return errorResponse(error);
  }
}

export async function POST(request: Request) {
  const body = await request.json();
  // `owner` is attribution, not a permission field (§1.17) — default it to the signed-in user
  // server-side when the client didn't set one, same spirit as the dashboard's viewer forwarding.
  const user = await getCurrentUser();
  try {
    const created = await createSource({ owner: user?.email ?? null, ...body });
    return NextResponse.json(created, { status: 201 });
  } catch (error) {
    return errorResponse(error);
  }
}
