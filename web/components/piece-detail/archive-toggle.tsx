"use client";

import * as React from "react";
import { Archive, ArchiveRestore, Loader2 } from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import type { PieceDetail } from "@/lib/pieces/types";

/**
 * Archive / unarchive (triage at scale) — deliberately NOT stage-gated, unlike every action in
 * `Pipeline`/`lib/pieces/actions.ts`: archiving is orthogonal to the stage machine (it must work
 * from any stage, including the terminal `published` stage), so it renders unconditionally in the
 * header rather than living inside that stage-contextual block (which instead dims itself when
 * archived — see `Pipeline`'s own doc). Purely a dashboard-visibility flag — firing it changes
 * nothing else about the piece, and is always reversible.
 */
export function ArchiveToggle({
  piece,
  onUpdated,
}: {
  piece: PieceDetail;
  onUpdated: (next: PieceDetail) => void;
}) {
  const [pending, setPending] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const archived = Boolean(piece.archived_at);

  async function fire(action: "archive" | "unarchive") {
    setPending(true);
    setError(null);
    try {
      const res = await fetch(`/api/pieces/${encodeURIComponent(piece.id)}/${action}`, {
        method: "POST",
      });
      if (!res.ok) {
        const body = (await res.json().catch(() => null)) as { error?: string } | null;
        throw new Error(body?.error ?? `request failed (${res.status})`);
      }
      const refreshed = await fetch(`/api/pieces/${encodeURIComponent(piece.id)}`, {
        cache: "no-store",
      });
      if (refreshed.ok) {
        onUpdated((await refreshed.json()) as PieceDetail);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "something went wrong");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() => fire(archived ? "unarchive" : "archive")}
        disabled={pending}
        title={
          archived
            ? "Restore this piece to the dashboard queue"
            : "Hide this piece from the dashboard queue — reversible, changes nothing else"
        }
      >
        {pending ? (
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
        ) : archived ? (
          <ArchiveRestore className="h-4 w-4" aria-hidden />
        ) : (
          <Archive className="h-4 w-4" aria-hidden />
        )}
        {archived ? "Unarchive" : "Archive"}
      </Button>
      {error ? <Alert>{error}</Alert> : null}
    </div>
  );
}
