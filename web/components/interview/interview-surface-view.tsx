"use client";

import * as React from "react";
import Link from "next/link";

import { AssignmentBanner } from "@/components/interview/assignment-banner";
import { CompletePanel } from "@/components/interview/complete-panel";
import { Composer } from "@/components/interview/composer";
import { ConversationPanel } from "@/components/interview/conversation-panel";
import { SessionPanel } from "@/components/interview/session-panel";
import { TranscriptPanel } from "@/components/interview/transcript-panel";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import type { Interview, RespondResult, TranscriptTurn } from "@/lib/interviews/types";
import { shouldNudgeWrapUp } from "@/lib/interviews/wrapup";

interface AssignmentPiece {
  id: string;
  title: string;
  voice: string;
  owner: string | null;
  target: string | null;
}

async function parseError(res: Response): Promise<string> {
  const body = (await res.json().catch(() => null)) as { error?: string } | null;
  return body?.error ?? `request failed (${res.status})`;
}

/**
 * The interview surface (cmw-ui-wireframes screen 3) — the interviewee view driving the merged
 * interview engine (D5-context-assembly §5) entirely through the `web/` BFF. Holds the Interview
 * and the sacred transcript as client state so a turn (ask → answer → recap, or a
 * research/meta/tangent branch) can update the screen in place without a full reload.
 *
 * Focused interview mode (cmw-interview-focused-mode): single-column, mobile-first — the question
 * (ConversationPanel) + the composer + the sacred transcript, plus the kept affordances (the
 * assignment banner, Edit + Recap on each turn, skip-without-pending-question, mark-complete,
 * and the stop-for-the-day / where-are-we session controls). The persona roster panel
 * (add/drop interviewer) is deliberately NOT part of the focused surface — that's a
 * coordinator move, fast-followed separately — and the D6 doctrine prose that used to sit under
 * the composer is hidden (the classification itself still runs on every submission). The route
 * itself (`app/interviews/[interviewId]/page.tsx`) mounts this in `InterviewShell`, so the
 * Dashboard/Spikes/Sources/Voice-kits nav chrome never renders here at all.
 */
export function InterviewSurfaceView({
  piece,
  initialInterview,
  initialTurns,
}: {
  piece: AssignmentPiece;
  initialInterview: Interview;
  initialTurns: TranscriptTurn[];
}) {
  const [interview, setInterview] = React.useState(initialInterview);
  const [turns, setTurns] = React.useState(initialTurns);
  const [lastResult, setLastResult] = React.useState<RespondResult | null>(null);
  const [sessionNote, setSessionNote] = React.useState<string | null>(null);

  const [askPending, setAskPending] = React.useState(false);
  const [askError, setAskError] = React.useState<string | null>(null);
  const [respondPending, setRespondPending] = React.useState(false);
  const [respondError, setRespondError] = React.useState<string | null>(null);
  const [completePending, setCompletePending] = React.useState(false);
  const [skipPending, setSkipPending] = React.useState(false);

  const canAct = Boolean(interview.current_question) && interview.status === "open";
  const rosterExhausted =
    !interview.current_question &&
    interview.current_persona_index >= interview.interviewer_personas.length;
  const activePersona =
    interview.interviewer_personas[interview.current_persona_index] ?? null;
  const showWrapUpNudge =
    interview.status === "open" &&
    !rosterExhausted &&
    shouldNudgeWrapUp(turns, activePersona, Boolean(interview.current_question));

  async function refreshInterview() {
    const res = await fetch(`/api/interviews/${interview.id}`, { cache: "no-store" });
    if (res.ok) setInterview((await res.json()) as Interview);
  }

  async function askNextQuestion() {
    setAskPending(true);
    setAskError(null);
    try {
      const res = await fetch(`/api/interviews/${interview.id}/next-question`, { method: "POST" });
      if (!res.ok) throw new Error(await parseError(res));
      setInterview((await res.json()) as Interview);
      setLastResult(null);
    } catch (e) {
      setAskError(e instanceof Error ? e.message : "something went wrong");
    } finally {
      setAskPending(false);
    }
  }

  async function submitResponse(text: string) {
    setRespondPending(true);
    setRespondError(null);
    try {
      const res = await fetch(`/api/interviews/${interview.id}/respond`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ text }),
      });
      if (!res.ok) throw new Error(await parseError(res));
      const result = (await res.json()) as RespondResult;
      setLastResult(result);
      if (result.op === "answer") {
        setTurns((prev) => [...prev, result.turn]);
        setInterview((prev) => ({ ...prev, current_question: null }));
      } else if (result.op === "meta-command") {
        // skip/go-back/add/drop/restart/stop-for-the-day all mutate roster/current_question
        // server-side beyond what the result itself carries — resync from the source of truth.
        await refreshInterview();
      }
      // research-this / tangent: the pending question is untouched, nothing to resync.
    } catch (e) {
      setRespondError(e instanceof Error ? e.message : "something went wrong");
    } finally {
      setRespondPending(false);
    }
  }

  async function skipPersona() {
    setSkipPending(true);
    setRespondError(null);
    try {
      const res = await fetch(`/api/interviews/${interview.id}/advance-persona`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ direction: "skip" }),
      });
      if (!res.ok) throw new Error(await parseError(res));
      const result = (await res.json()) as RespondResult;
      setLastResult(result);
      await refreshInterview();
    } catch (e) {
      setRespondError(e instanceof Error ? e.message : "something went wrong");
    } finally {
      setSkipPending(false);
    }
  }

  async function markComplete() {
    setCompletePending(true);
    try {
      const res = await fetch(`/api/interviews/${interview.id}/mark-complete`, { method: "POST" });
      if (!res.ok) throw new Error(await parseError(res));
      setInterview((await res.json()) as Interview);
    } finally {
      setCompletePending(false);
    }
  }

  async function editAnswer(turnId: string, text: string) {
    const res = await fetch(
      `/api/pieces/${piece.id}/transcript/turns/${encodeURIComponent(turnId)}`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ text, interview_id: interview.id }),
      },
    );
    if (!res.ok) throw new Error(await parseError(res));
    const updated = (await res.json()) as TranscriptTurn;
    setTurns((prev) => prev.map((t) => (t.id === turnId ? updated : t)));
  }

  async function recapTurn(turnId: string): Promise<string> {
    const res = await fetch(
      `/api/pieces/${piece.id}/transcript/turns/${encodeURIComponent(turnId)}/recap`,
      { method: "POST" },
    );
    if (!res.ok) throw new Error(await parseError(res));
    return ((await res.json()) as { recap: string }).recap;
  }

  async function stopForDay() {
    setSessionNote(null);
    await submitResponse("Let's stop for today.");
    setSessionNote("If classified as stop-for-the-day, the piece is now paused — resumable here.");
  }

  async function whereAreWe() {
    setSessionNote(null);
    await submitResponse("Where are we? Please reorient me.");
  }

  return (
    <div className="flex flex-col gap-6">
      <Button asChild variant="ghost" size="sm" className="-ml-2 w-fit">
        <Link href="/content-machine">&larr; Back to dashboard</Link>
      </Button>

      <AssignmentBanner piece={piece} interview={interview} />

      <ConversationPanel
        interview={interview}
        turns={turns}
        lastResult={lastResult}
        rosterExhausted={rosterExhausted}
        askPending={askPending}
        askError={askError}
        onAskNextQuestion={askNextQuestion}
        showWrapUpNudge={showWrapUpNudge}
        onSkip={skipPersona}
        skipPending={skipPending}
      />
      {/* Stays mounted (disabled) even with no pending question, so the last detected op
          chip remains visible as a confirmation until the next question is asked. */}
      <Composer
        disabled={!canAct}
        pending={respondPending}
        skipDisabled={interview.status !== "open" || rosterExhausted}
        skipPending={skipPending}
        lastOp={lastResult?.op ?? null}
        onSubmit={submitResponse}
        onSkip={skipPersona}
      />
      {respondError ? <Alert>{respondError}</Alert> : null}

      <TranscriptPanel
        turns={turns}
        editable={interview.status === "open"}
        onEdit={editAnswer}
        onRecap={recapTurn}
      />
      <CompletePanel
        status={interview.status}
        pending={completePending}
        onMarkComplete={markComplete}
      />
      <SessionPanel
        canAct={canAct}
        pending={respondPending}
        note={sessionNote}
        onStopForDay={stopForDay}
        onWhereAreWe={whereAreWe}
      />
    </div>
  );
}
