"use client";

import * as React from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import type { Narrative } from "@/lib/narratives/types";

/**
 * "Where did my narrative go?" (cmw-first-run-ux-batch item 6) — a spike whose `origin.kind` is
 * `"narrative"` was seeded from a full spoken narrative (the Radar's "Your narrative" textarea),
 * but nothing downstream of that page ever showed the text again; only the distilled headline
 * survives onto the spike. The full `seed_text` was always retained server-side
 * (`agents/app/narratives.py`'s `GET /api/narratives/{id}`) — this just gives it a UI. Loads
 * on demand rather than on mount, so picking a spike never fires an extra request nobody asked
 * for.
 */
export function NarrativeReveal({
  narrativeId,
  subject = "the narrative that produced this spike",
}: {
  narrativeId: string;
  /** The toggle button reads "View {subject}" / "Hide {subject}" — override for a caller whose
   * context isn't literally "a spike" (e.g. piece-detail, where the narrative produced the
   * piece's origin spike, not the piece directly). Defaults to the original spike-kickoff copy so
   * every existing caller is unaffected. */
  subject?: string;
}) {
  const [narrative, setNarrative] = React.useState<Narrative | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [expanded, setExpanded] = React.useState(false);

  async function handleToggle() {
    if (expanded) {
      setExpanded(false);
      return;
    }
    setExpanded(true);
    if (narrative || loading) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/narratives/${encodeURIComponent(narrativeId)}`);
      const body: unknown = await res.json();
      if (!res.ok) {
        throw new Error(
          body && typeof body === "object" && "error" in body
            ? String((body as { error: unknown }).error)
            : "could not load the originating narrative",
        );
      }
      setNarrative(body as Narrative);
    } catch (err) {
      setError(err instanceof Error ? err.message : "could not load the originating narrative");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col gap-2 mt-1">
      <Button type="button" variant="outline" size="sm" onClick={handleToggle} className="self-start">
        {expanded ? "Hide" : "View"} {subject}
      </Button>
      {expanded ? (
        loading ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : error ? (
          <Alert>{error}</Alert>
        ) : narrative ? (
          <p className="whitespace-pre-wrap rounded-md border bg-muted/30 px-3 py-2 text-sm">
            {narrative.seed_text}
          </p>
        ) : null
      ) : null}
    </div>
  );
}
