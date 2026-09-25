import { notFound } from "next/navigation";

import { AppShell } from "@/components/shell/app-shell";
import { ReviewRoundView } from "@/components/review-round/review-round-view";
import { AgentsRequestError, fetchPieceDetail } from "@/lib/agents-client";
import { requireUser } from "@/lib/session";

/**
 * The review-round screen (cmw-ui-wireframes screen 04; D4/D11; open-decisions Item 7): mint an
 * internal/external Doc from the current revision, preview what a "reviews done" would fold in,
 * and only then confirm — mounted from the piece-detail screen's review-stage primary action
 * (a LINK, never a blind trigger; distinct from "Finalize", Item 7). Same fetch/auth pattern as
 * `/pieces/[pieceId]` and `/pieces/[pieceId]/finalize`: read-only server fetch through the BFF,
 * then hand off to a client component that holds the piece as state.
 */
export default async function ReviewRoundPage({
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
        <ReviewRoundView initial={piece} />
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
