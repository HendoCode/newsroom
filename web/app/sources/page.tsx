import { AppShell } from "@/components/shell/app-shell";
import { SourceRegistry } from "@/components/sources/source-registry";
import { fetchSources } from "@/lib/agents-client";
import type { SourceListResponse } from "@/lib/sources/types";
import { requireUser } from "@/lib/session";

/**
 * The source registry: manage what the Oracle reads (Item 6 / D8; cmw-ui-wireframes screen 7).
 * Mounts into the existing app shell/routing exactly like the dashboard. Work-state is read
 * through the data layer via the BFF client (`fetchSources`, server-only) — if the agents service
 * is unreachable we still render the shell with an empty registry rather than erroring the whole
 * page; the screen's own refresh path retries through `/api/sources`.
 *
 * `force-dynamic` (matching `/api/sources`'s own directive) so this initial render is never
 * served from a stale Full Route Cache entry — the client mutations below (create/edit/toggle/
 * retire) go through plain `fetch()` to Route Handlers, which Next.js has no way to know should
 * invalidate a cached render of this page (that's only automatic for Server Actions). Paired with
 * `SourceRegistry`'s own `router.refresh()` calls after each mutation, which invalidate the
 * client-side Router Cache too — without both, a source added here could appear to vanish after
 * navigating away and back (cmw-source-registry-ux item 1: reproduced live via a real browser
 * hitting the back button, not just reasoned about — see that PR description).
 */
export const dynamic = "force-dynamic";

export default async function SourcesPage() {
  const user = await requireUser();

  let initial: SourceListResponse;
  try {
    initial = await fetchSources();
  } catch {
    initial = { source: "seed", items: [] };
  }

  return (
    <AppShell user={user} active="sources">
      <SourceRegistry initial={initial} />
    </AppShell>
  );
}
