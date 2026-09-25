import { NextResponse } from "next/server";

import { AgentsRequestError, fetchContentWorkflowDesk } from "@/lib/agents-client";
import { getCurrentUser } from "@/lib/session";

/**
 * BFF for server-owned Desk projection (obligations, machine work, library).
 */
export const dynamic = "force-dynamic";

export async function GET() {
  const user = await getCurrentUser();
  try {
    const desk = await fetchContentWorkflowDesk(user?.email);
    return NextResponse.json(desk);
  } catch (error) {
    const status = error instanceof AgentsRequestError ? error.status : 502;
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "unknown error" },
      { status },
    );
  }
}
