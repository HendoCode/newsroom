import { Loader2 } from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { metaCommandLabel } from "@/lib/interviews/ops";
import { personaLabel } from "@/lib/interviews/personas";
import type { Interview, RespondResult, TranscriptTurn } from "@/lib/interviews/types";

const RECENT_TURNS = 3;

/**
 * The center one-question-per-turn conversation (cmw-ui-wireframes screen 3): recent history,
 * the active persona's current question ("your turn"), and — once answered — the machine's
 * "here's what I heard" recap as a read-only confirmation view over the interviewee's own words,
 * never a replacement for them (D16b). Research/meta/tangent results render as their own inline
 * outcomes rather than being folded into the transcript.
 */
export function ConversationPanel({
  interview,
  turns,
  lastResult,
  rosterExhausted,
  askPending,
  askError,
  onAskNextQuestion,
  showWrapUpNudge,
  onSkip,
  skipPending,
}: {
  interview: Interview;
  turns: TranscriptTurn[];
  lastResult: RespondResult | null;
  rosterExhausted: boolean;
  askPending: boolean;
  askError: string | null;
  onAskNextQuestion: () => void;
  /** v1 heuristic (`lib/interviews/wrapup.ts`) — a nudge, never a block: skipping stays a click
   * away below, but so does asking yet another question if the interviewee wants to keep going. */
  showWrapUpNudge: boolean;
  onSkip: () => void;
  skipPending: boolean;
}) {
  const activePersona =
    interview.interviewer_personas[interview.current_persona_index] ?? null;
  const recent = turns.slice(-RECENT_TURNS);

  return (
    <div className="rounded-lg border bg-card p-4">
      {activePersona ? (
        <h3 className="font-serif text-base font-semibold">
          {personaLabel(activePersona)}
        </h3>
      ) : null}

      {showWrapUpNudge ? (
        <div className="mt-2 flex flex-wrap items-center justify-between gap-2 rounded-md border border-dashed bg-muted/20 px-3 py-2 text-xs text-muted-foreground">
          <span>
            {activePersona ? personaLabel(activePersona) : "This interviewer"} has asked a good
            number of questions already — feel free to keep going, or move on.
          </span>
          <Button size="sm" variant="outline" onClick={onSkip} disabled={skipPending}>
            {skipPending ? <Loader2 className="h-3 w-3 animate-spin" aria-hidden /> : null}
            Skip to next persona
          </Button>
        </div>
      ) : null}

      <div className="mt-3 flex flex-col gap-3">
        {recent.map((turn) => (
          <div key={turn.id} className="flex flex-col gap-1.5">
            <div className="rounded-md border bg-muted/30 px-3 py-2 text-sm">
              <div className="text-[10px] uppercase text-muted-foreground">
                {personaLabel(turn.persona)} &middot; question
              </div>
              {turn.question}
            </div>
            <div className="rounded-md border px-3 py-2 text-sm">
              <div className="text-[10px] uppercase text-muted-foreground">your answer</div>
              {turn.answer}
            </div>
          </div>
        ))}

        {interview.current_question ? (
          <div className="rounded-md border-2 border-primary px-3 py-2 text-sm">
            <div className="text-[10px] uppercase text-muted-foreground">
              question &middot; your turn
            </div>
            {interview.current_question}
          </div>
        ) : rosterExhausted ? (
          <div className="rounded-md border border-dashed px-3 py-3 text-center text-sm text-muted-foreground">
            Every interviewer in the roster has had a turn. Review your answers below, or
            mark the interview complete when you&rsquo;re ready.
          </div>
        ) : (
          <div className="flex flex-col items-center gap-2 rounded-md border border-dashed px-3 py-4">
            <Button onClick={onAskNextQuestion} disabled={askPending}>
              {askPending ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : null}
              Ask next question
            </Button>
            {askError ? <Alert className="text-xs">{askError}</Alert> : null}
          </div>
        )}

        {lastResult?.op === "answer" ? (
          <div className="rounded-md border border-dashed bg-muted/20 px-3 py-2 text-sm">
            <div className="text-[10px] uppercase text-muted-foreground">
              Here&rsquo;s what I heard &mdash; confirming your words, not a new draft
            </div>
            {lastResult.recap}
          </div>
        ) : null}

        {lastResult?.op === "research-this" ? (
          <div className="rounded-md border border-dashed bg-muted/20 px-3 py-2 text-sm">
            <div className="text-[10px] uppercase text-muted-foreground">Research</div>
            {lastResult.answer}
            {lastResult.resume_question ? (
              <p className="mt-1 text-xs text-muted-foreground">
                Picking back up: {lastResult.resume_question}
              </p>
            ) : null}
          </div>
        ) : null}

        {lastResult?.op === "meta-command" ? (
          <div className="rounded-md border border-dashed bg-muted/20 px-3 py-2 text-xs text-muted-foreground">
            {lastResult.handled
              ? `Applied: ${metaCommandLabel(lastResult.command)}.`
              : `Noted, not applied here: ${metaCommandLabel(lastResult.command)}${lastResult.note ? ` — ${lastResult.note}` : ""}`}
          </div>
        ) : null}

        {lastResult?.op === "tangent" ? (
          <div className="rounded-md border border-dashed bg-muted/20 px-3 py-2 text-xs text-muted-foreground">
            Parked to the Vault as spike <span className="font-mono">{lastResult.spike_id}</span> —
            nothing is thrown away.
          </div>
        ) : null}
      </div>
    </div>
  );
}
