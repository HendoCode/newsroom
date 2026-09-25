import { AppShell } from "@/components/shell/app-shell";
import { SpikeVaultBrowser } from "@/components/spikes/spike-vault-browser";
import { fetchSpikes } from "@/lib/agents-client";
import type { SpikeListResponse } from "@/lib/spikes/types";
import { requireUser } from "@/lib/session";

/**
 * The Spikes & Vault browser (D15; cmw-ui-wireframes screen 5). Mounts into the existing app
 * shell exactly like the dashboard/source-registry. Work-state is read through the data layer via
 * the BFF client (`fetchSpikes`, server-only) — if the agents service is unreachable we still
 * render the shell with an empty pool rather than erroring the whole page; the screen's own
 * refresh path retries through `/api/spikes`.
 */
export default async function SpikesPage() {
  const user = await requireUser();

  let initial: SpikeListResponse;
  try {
    initial = await fetchSpikes();
  } catch {
    initial = { source: "seed", items: [] };
  }

  return (
    <AppShell user={user} active="spikes">
      <SpikeVaultBrowser initial={initial} />
    </AppShell>
  );
}
