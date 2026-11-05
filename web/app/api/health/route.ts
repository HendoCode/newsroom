import { NextResponse } from "next/server";

// web/ own liveness probe (docs/design.md §6). Used by docker compose healthcheck.
export const dynamic = "force-dynamic";

export function GET() {
  return NextResponse.json({ status: "ok", service: "web" });
}
