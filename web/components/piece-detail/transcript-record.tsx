"use client";

import * as React from "react";
import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Modal } from "@/components/ui/modal";
import { isLongAnswer } from "@/lib/interviews/answer-length";
import { personaLabel } from "@/lib/interviews/personas";
import type { TranscriptTurn } from "@/lib/interviews/types";
import type { InterviewRecord } from "@/lib/pieces/types";

/**
 * Piece-detail's only route back to the sacred transcript (D16b) once the kickoff share link
 * (`spike-kickoff.tsx`) is out of view — a pause or a completion otherwise leaves it unreachable.
 * Genuinely read-only: no edit/recap handlers exist on this component at all, unlike the
 * interactive interview surface (`transcript-panel.tsx`), so there is no control to hide, only
 * one to omit. Hendo's call (2026-08-08): a still-open interview legitimately stays resumable at
 * that interactive surface (a "Resume interview" link), but a `complete` one must never be — so
 * only `status === "open"` interviews get that link.
 *
 * `interviews` is rendered as its own list (not a single "the interview" summary), numbered "Round
 * N" in the order the piece's Interview sessions were opened (`InterviewRepository.by_piece` now
 * sorts on `_id` for exactly this — agents/AGENTS.md) — the genuinely available attribution for
 * "which round is which" (D16a's route-to-interview re-opens review → interviewing for another
 * round; is_gap_interview marks one). `turns` renders below as one shared block, matching the real
 * wire shape: `GET .../transcript/turns` returns one piece-scoped, unattributed turn list, never
 * split per round — `agents/app/interview/transcript.py`'s anchor only ever records a turn's
 * persona and id, never which Interview session produced it (PR #64). So a turn cannot honestly be
 * shown nested under "its" round; the note below says so instead of implying an attribution the
 * data doesn't support. Kept as two separate props/sections so a future change that DID add
 * per-turn interview attribution could nest turns under their round without restructuring this
 * component.
 *
 * Each turn's answer is rendered by `TurnAnswer` below (cmw-modal-long-text-elsewhere), which
 * reuses `components/ui/modal.tsx`'s `Modal` — the same clamp-then-modal pattern `DraftView`
 * established — once an answer is genuinely long (`lib/interviews/answer-length.ts`).
 */
export function TranscriptRecord({
  interviews,
  turns,
  originSpikeId,
}: {
  interviews: InterviewRecord[];
  turns: TranscriptTurn[];
  /** The Spike this piece was picked from, if any — when a piece genuinely has zero Interviews
   * (a piece created before cmw-piece-interviewing-without-interview closed that gap, since a
   * fresh pick now opens one atomically), this is the only route back to the kickoff screen that
   * can open one: piece-detail itself has no interview-creation control of its own. */
  originSpikeId?: string | null;
}) {
  return (
    <div className="flex flex-col gap-4">
      {interviews.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No interviews opened yet.{" "}
          {originSpikeId ? (
            <Link href={`/spikes/${originSpikeId}`} className="underline">
              Open the kickoff screen
            </Link>
          ) : null}
        </p>
      ) : (
        <ul className="flex flex-col gap-2">
          {interviews.map((interview, index) => (
            <li
              key={interview.interview_id}
              className="flex flex-wrap items-center justify-between gap-2 rounded-md border px-3 py-2 text-sm"
            >
              <span className="min-w-0">
                <span className="font-medium">Round {index + 1}</span>
                {" — "}
                {interview.about ?? "Interview"}
                {interview.assigned_expert ? (
                  <span className="text-muted-foreground"> &middot; {interview.assigned_expert}</span>
                ) : null}
                <Badge variant={interview.status === "open" ? "outline" : "muted"} className="ml-1.5">
                  {interview.status}
                </Badge>
                {interview.is_gap_interview ? (
                  <Badge variant="outline" className="ml-1">
                    gap
                  </Badge>
                ) : null}
              </span>
              {interview.status === "open" ? (
                <Button asChild size="sm" variant="secondary">
                  <Link href={`/interviews/${interview.interview_id}`}>Resume interview</Link>
                </Button>
              ) : null}
            </li>
          ))}
        </ul>
      )}

      <div>
        <h4 className="text-xs font-medium uppercase text-muted-foreground">Transcript</h4>
        {interviews.length > 1 ? (
          <p className="mt-1 text-xs text-muted-foreground">
            One shared transcript across every round above — each turn records its persona, not
            which round produced it, so turns below can&rsquo;t be split out per round.
          </p>
        ) : null}
        {turns.length === 0 ? (
          <p className="mt-1.5 text-sm text-muted-foreground">No interview turns recorded yet.</p>
        ) : (
          <ul className="mt-1.5 flex flex-col gap-2">
            {turns.map((turn) => (
              <li key={turn.id} className="rounded-md border px-3 py-2 text-sm">
                <div className="text-[10px] uppercase text-muted-foreground">
                  {personaLabel(turn.persona)}
                </div>
                <div className="mt-0.5 text-xs text-muted-foreground">{turn.question}</div>
                <TurnAnswer turn={turn} />
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

/**
 * A turn's answer, clamped to 3 lines with a "Read full answer" modal once it's long — this is
 * the exact gap Hendo hit personally ("a modal popup of the complete text" for a long
 * research-derived answer). Matches `DraftView`'s clamp-first pattern: a short answer (the common
 * case) renders in full with no button at all, never hidden behind a click by default.
 */
function TurnAnswer({ turn }: { turn: TranscriptTurn }) {
  const [open, setOpen] = React.useState(false);

  if (!isLongAnswer(turn.answer)) {
    return <p className="mt-1">{turn.answer}</p>;
  }

  return (
    <div className="mt-1 flex flex-col gap-1.5">
      <p className="line-clamp-3">{turn.answer}</p>
      <Button variant="outline" size="sm" className="self-start" onClick={() => setOpen(true)}>
        Read full answer
      </Button>
      <Modal
        open={open}
        onOpenChange={setOpen}
        title={`${personaLabel(turn.persona)} — full answer`}
        description={turn.question}
      >
        <p className="whitespace-pre-wrap text-sm">{turn.answer}</p>
      </Modal>
    </div>
  );
}
