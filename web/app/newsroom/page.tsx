import { AppShell } from "@/components/shell/app-shell";
import { Dashboard } from "@/components/dashboard/dashboard";
import { fetchDashboard } from "@/lib/agents-client";
import type { DashboardResponse } from "@/lib/dashboard/types";
import { requireUser } from "@/lib/session";

/**
 * Newsroom home: the redesigned desk (Inbox + Machine strip + Library).
 *
 * Lives at `/newsroom` — the post-login hub (`app/page.tsx`) is the platform landing
 * destination; this route is what its "Newsroom" card opens into. The PR #120 Operator
 * Desk tracer is no longer the home screen (it leaked internal enum names into copy and only
 * listed ~6 recent pieces). Middleware gates this route; `requireUser()` yields the typed
 * signed-in user and redirects to /signin as defense-in-depth.
 *
 * Work-state is read through the data layer via the BFF client (`fetchDashboard`, server-only) —
 * the `web/` service holds no work-state and runs no orchestration (D5). If the agents service is
 * unreachable we still render the shell with an empty queue rather than erroring the whole page;
 * the dashboard's Refresh button retries through the `/api/dashboard` BFF route.
 */
export const dynamic = "force-dynamic";

export default async function NewsroomHome() {
  const user = await requireUser();

  let initial: DashboardResponse;
  try {
    initial = await fetchDashboard(user.email);
  } catch {
    initial = { source: "seed", items: [] };
  }

  return (
    <AppShell user={user} active="dashboard">
      <Dashboard initial={initial} email={user.email} />
    </AppShell>
  );
}
