import { NextResponse } from "next/server";

import { AgentsRequestError, fetchPersonas } from "@/lib/agents-client";
import type { PersonaKind } from "@/lib/brain/types";

/** BFF route listing the Git brain's persona roster — populates the kickoff screen's interviewer
 * picker (cmw-ui-wireframes screen 6 step 4) without hardcoding a list that would drift from the
 * brain. `kind` defaults to `interviewer`; whitelisted server-side against the two real kinds. */
export const dynamic = "force-dynamic";

function isPersonaKind(value: string | null): value is PersonaKind {
  return value === "interviewer" || value === "editor";
}

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const raw = searchParams.get("kind");
  const kind: PersonaKind = isPersonaKind(raw) ? raw : "interviewer";
  try {
    const data = await fetchPersonas(kind);
    return NextResponse.json(data);
  } catch (error) {
    const status = error instanceof AgentsRequestError ? error.status : 502;
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "unknown error" },
      { status },
    );
  }
}
