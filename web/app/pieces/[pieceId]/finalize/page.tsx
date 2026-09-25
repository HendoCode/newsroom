import { notFound } from "next/navigation";

import { FinalizeView } from "@/components/finalize/finalize-view";
import { AppShell } from "@/components/shell/app-shell";
import { AgentsRequestError, fetchPieceDetail } from "@/lib/agents-client";
import { requireUser } from "@/lib/session";

/**
 * Finalize / outputs (cmw-ui-wireframes screen 10; use case J; D13/open-decisions Item 5): select
 * output formats, review the warn-not-block pre-finalize checks, and fire the finalize step —
 * mounted from the piece-detail screen's "Finalize" secondary action (distinct from "Reviews
 * done", Item 7). Same fetch/auth pattern as `/pieces/[pieceId]`: read-only server fetch through
 * the BFF, then hand off to a client component that holds the piece as state.
 */
export default async function FinalizeOutputsPage({
  params,
}: {
  params: Promise<{ pieceId: string }>;
}) {
  const user = await requireUser();
  const { pieceId } = await params;

  try {
    const piece = await fetchPieceDetail(pieceId, user.email);
    return (
      <AppShell user={user}>
        <FinalizeView initial={piece} />
      </AppShell>
    );
  } catch (error) {
    if (error instanceof AgentsRequestError && error.status === 404) {
      notFound();
    }
    return (
      <AppShell user={user}>
        <div className="mx-auto max-w-lg rounded-lg border border-dashed bg-card p-6 text-center">
          <p className="font-serif text-lg font-semibold">Piece unreachable</p>
          <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
            The agents service didn&rsquo;t respond:{" "}
            {error instanceof Error ? error.message : "unknown error"}. Try refreshing, or check
            that the agents service is running.
          </p>
        </div>
      </AppShell>
    );
  }
}
