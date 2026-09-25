import { NextResponse } from "next/server";

import { AgentsRequestError, createNarrative } from "@/lib/agents-client";
import { getCurrentUser } from "@/lib/session";

/**
 * BFF route for creating a Narrative (§1.5) — the audience/angle-intent seed Oracle Entry B runs
 * against (cmw-ui-wireframes screen 8). `author` is attribution, defaulted server-side to the
 * signed-in user, same convention as the source registry's `POST`.
 */
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const body = await request.json();
  const user = await getCurrentUser();
  try {
    const created = await createNarrative({ author: user?.email ?? null, ...body });
    return NextResponse.json(created, { status: 201 });
  } catch (error) {
    const status = error instanceof AgentsRequestError ? error.status : 502;
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "unknown error" },
      { status },
    );
  }
}
