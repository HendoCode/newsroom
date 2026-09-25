import { notFound } from "next/navigation";

import { InterviewSurfaceView } from "@/components/interview/interview-surface-view";
import { InterviewShell } from "@/components/shell/interview-shell";
import {
  AgentsRequestError,
  fetchInterview,
  fetchPieceDetail,
  fetchTranscriptTurns,
} from "@/lib/agents-client";
import { requireUser } from "@/lib/session";

/**
 * The interview surface (cmw-ui-wireframes screen 3) — the SSO-gated expert deep link
 * (docs/design.md D10, use case C) an assigned interviewee opens, mobile-friendly since it's
 * commonly opened from a shared Slack link on a phone. Auth-gated like every screen (middleware +
 * `requireUser()`); drives the merged interview engine (serial personas, D6 classification, the
 * sacred transcript, the research sidecar, and the recap) entirely through the BFF client — never
 * reimplementing engine logic here.
 *
 * Focused interview mode (cmw-interview-focused-mode): this route mounts into `InterviewShell`
 * instead of `AppShell` — the interviewee is an external expert mid-question, not an operator
 * browsing the app, so the Dashboard/Spikes/Sources/Voice-kits nav chrome is dropped entirely
 * (and so is the D6 doctrine prose in the composer, see `components/interview/composer.tsx`).
 * The engine itself is untouched: classification still runs on every submission.
 */
export default async function InterviewSurfacePage({
  params,
}: {
  params: Promise<{ interviewId: string }>;
}) {
  const user = await requireUser();
  const { interviewId } = await params;

  let interview;
  try {
    interview = await fetchInterview(interviewId);
  } catch (error) {
    if (error instanceof AgentsRequestError && error.status === 404) {
      notFound();
    }
    return (
      <InterviewShell user={user}>
        <UnreachableCard error={error} />
      </InterviewShell>
    );
  }

  try {
    const [piece, turns] = await Promise.all([
      fetchPieceDetail(interview.piece_id, user.email),
      fetchTranscriptTurns(interview.piece_id),
    ]);
    return (
      <InterviewShell user={user}>
        <InterviewSurfaceView
          piece={{
            id: piece.id,
            title: piece.title,
            voice: piece.voice,
            owner: piece.owner,
            target: piece.target,
          }}
          initialInterview={interview}
          initialTurns={turns}
        />
      </InterviewShell>
    );
  } catch (error) {
    return (
      <InterviewShell user={user}>
        <UnreachableCard error={error} />
      </InterviewShell>
    );
  }
}

function UnreachableCard({ error }: { error: unknown }) {
  return (
    <div className="mx-auto max-w-lg rounded-lg border border-dashed bg-card p-6 text-center">
      <p className="font-serif text-lg font-semibold">Interview unreachable</p>
      <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
        The agents service didn&rsquo;t respond:{" "}
        {error instanceof Error ? error.message : "unknown error"}. Try refreshing, or check that
        the agents service is running.
      </p>
    </div>
  );
}
