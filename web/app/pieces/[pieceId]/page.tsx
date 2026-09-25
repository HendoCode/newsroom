import { notFound } from "next/navigation";

import { PieceDetailView } from "@/components/piece-detail/piece-detail-view";
import { AppShell } from "@/components/shell/app-shell";
import {
  AgentsRequestError,
  fetchPersonas,
  fetchPieceDetail,
  fetchSpike,
  fetchTranscriptTurns,
} from "@/lib/agents-client";
import type { TranscriptTurn } from "@/lib/interviews/types";
import { requireUser } from "@/lib/session";
import { originNarrativeId } from "@/lib/spikes/origin";

/**
 * Piece detail (cmw-ui-wireframes screen 2): one piece across its whole lifecycle, mounted from
 * the dashboard's stage-contextual card actions. Auth-gated like every screen (middleware +
 * `requireUser()`); reads real piece work-state through the data layer via the BFF client
 * (`fetchPieceDetail`, server-only — the same pattern the dashboard's landing page uses).
 */
export default async function PieceDetailPage({
  params,
}: {
  params: Promise<{ pieceId: string }>;
}) {
  const user = await requireUser();
  const { pieceId } = await params;

  try {
    const piece = await fetchPieceDetail(pieceId, user.email);
    // A piece whose interview(s) never produced a transcript file 404s here (§1.12/D16b: the
    // transcript is written lazily, on the first answered turn) — that's "nothing recorded yet,"
    // not a reason to fail the whole piece-detail page.
    let turns: TranscriptTurn[] = [];
    try {
      turns = await fetchTranscriptTurns(pieceId);
    } catch {
      turns = [];
    }
    // Only the review stage's "Start another round of interviews" secondary action needs this
    // roster (`Pipeline`) — fetched unconditionally anyway, same as the kickoff screen's pattern,
    // since it's a cheap read and the stage can change under a fired trigger without a page reload.
    const interviewerPersonas = await fetchPersonas("interviewer").then(
      (r) => r.personas,
      () => [] as string[],
    );
    // A piece can exist with no originating narrative at all (no origin spike, or one seeded some
    // other way than a spoken narrative) — that's a normal, non-error state, not something to
    // surface as a page failure.
    let narrativeId: string | null = null;
    if (piece.origin_spike_id) {
      try {
        narrativeId = originNarrativeId(await fetchSpike(piece.origin_spike_id));
      } catch {
        narrativeId = null;
      }
    }
    return (
      <AppShell user={user}>
        <PieceDetailView
          initial={piece}
          initialTurns={turns}
          interviewerPersonas={interviewerPersonas}
          originNarrativeId={narrativeId}
        />
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
