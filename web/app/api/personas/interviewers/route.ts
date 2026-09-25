import { NextResponse } from "next/server";

import { AgentsRequestError, fetchInterviewerPersonas } from "@/lib/agents-client";

/**
 * BFF route for the interview surface's persona menu (cmw-ui-wireframes screen 3) — the full
 * ~10-persona interviewer roster (§1.2), same store-nothing proxy pattern as `/api/dashboard`.
 */
export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const data = await fetchInterviewerPersonas();
    return NextResponse.json(data);
  } catch (error) {
    const status = error instanceof AgentsRequestError ? error.status : 502;
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "unknown error" },
      { status },
    );
  }
}
