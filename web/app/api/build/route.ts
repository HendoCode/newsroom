import { NextResponse } from "next/server";
import { readFileSync } from "fs";
import path from "path";

// Public, unauthenticated build metadata for both components (baked at image build).
// Safe: only commit SHAs + timestamps, no secrets/env. Cache: force-dynamic so fresh after redeploy.
export const dynamic = "force-dynamic";

export async function GET() {
  const webBuildPath = path.join(process.cwd(), "public", ".well-known", "cmw-build.json");
  let web: Record<string, unknown> = { component: "web", commit: "unknown", shortCommit: "unknown", builtAt: null };
  try {
    const raw = readFileSync(webBuildPath, "utf8");
    web = JSON.parse(raw);
  } catch {
    // fallback in dev
  }

  let agents: Record<string, unknown> = { component: "agents", commit: "unknown", shortCommit: "unknown", builtAt: null };
  const agentsUrl = process.env.AGENTS_URL || "http://agents:8000";
  try {
    const res = await fetch(`${agentsUrl}/build`, { cache: "no-store" });
    if (res.ok) {
      agents = await res.json();
    }
  } catch {
    // degraded: agents not reachable or not yet updated; return web only
  }

  return NextResponse.json({ web, agents });
}
