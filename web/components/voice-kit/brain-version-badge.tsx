import { Badge } from "@/components/ui/badge";
import type { BrainStatus } from "@/lib/agents-client";

/**
 * "Which brain am I running" (D1/D2): the commit-ish of the on-disk brain clone
 * (`HendoCode/content-machine-brain`) the agents service currently has checked out. Voice-kit is
 * the screen most directly about brain content, so this lives here rather than in the shared
 * `AppShell` — scoping it avoids threading a new fetch through every other page.
 */
export function BrainVersionBadge({ status }: { status: BrainStatus | null }) {
  if (!status || !status.connected) {
    return (
      <Badge variant="warning" title="The agents service can't reach a brain clone right now.">
        brain: unavailable
      </Badge>
    );
  }

  const shortSha = status.commit_sha ? status.commit_sha.slice(0, 8) : "unknown";
  const title = [
    status.remote_url ? `remote: ${status.remote_url}` : null,
    status.commit_message ? `"${status.commit_message}"` : null,
    status.commit_date,
  ]
    .filter(Boolean)
    .join(" — ");

  return (
    <Badge variant="outline" className="font-mono" title={title || undefined}>
      brain: {shortSha}
    </Badge>
  );
}
