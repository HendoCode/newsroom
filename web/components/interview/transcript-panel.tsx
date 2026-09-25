"use client";

import * as React from "react";
import { Loader2 } from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Modal } from "@/components/ui/modal";
import { TextArea } from "@/components/ui/textarea";
import { isLongAnswer } from "@/lib/interviews/answer-length";
import { personaLabel } from "@/lib/interviews/personas";
import type { TranscriptTurn } from "@/lib/interviews/types";
import { cn } from "@/lib/utils";

/**
 * "Review & edit my answers" (cmw-ui-wireframes screen 3): the sacred transcript (D16b) — every
 * answer is freely editable by the interviewee while this interview is `open`, and each can show
 * the machine's "here's what I heard" recap on demand as a read-only confirmation view (never
 * auto-written back over the stored answer). Once the interview is `complete`, `editable` is
 * false and the Edit control is omitted entirely (Hendo, 2026-08-08) — the transcript becomes
 * read-only, matching `piece-detail`'s own read-only transcript view. The agents-side edit route
 * enforces this independently (refuses the write once the named interview is complete), so this
 * is a courtesy — hiding the button, not the real gate.
 *
 * Recap stays available regardless of `editable`: it never writes back over the stored answer
 * (see `agents/app/interview/recap.py`), so completion has no reason to disable it.
 *
 * A long research-derived answer's *read* view clamps to 3 lines with a "Full answer" modal
 * (`lib/interviews/answer-length.ts`, the same threshold `transcript-record.tsx`'s read-only
 * piece-detail view uses) — Hendo's explicit ask for "a modal popup of the complete text." The
 * *edit* textarea is never clamped: it always holds the complete `turn.answer`, since editing
 * needs the full text regardless of how the read view displays it.
 */
export function TranscriptPanel({
  turns,
  editable,
  onEdit,
  onRecap,
}: {
  turns: TranscriptTurn[];
  editable: boolean;
  onEdit: (turnId: string, text: string) => Promise<void>;
  onRecap: (turnId: string) => Promise<string>;
}) {
  return (
    <div className="rounded-lg border bg-card p-4">
      <h3 className="font-serif text-base font-semibold">Review &amp; edit my answers</h3>
      <p className="mt-1 text-xs text-muted-foreground">
        The transcript is the <b className="text-foreground">source of truth</b>.{" "}
        {editable
          ? "You can freely edit anything you said."
          : "This interview is complete, so the transcript is read-only."}
      </p>

      {turns.length === 0 ? (
        <p className="mt-3 text-sm text-muted-foreground">No answers recorded yet.</p>
      ) : (
        <ul className="mt-3 flex flex-col gap-2">
          {turns.map((turn) => (
            <TranscriptTurnRow
              key={turn.id}
              turn={turn}
              editable={editable}
              onEdit={onEdit}
              onRecap={onRecap}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

function TranscriptTurnRow({
  turn,
  editable,
  onEdit,
  onRecap,
}: {
  turn: TranscriptTurn;
  editable: boolean;
  onEdit: (turnId: string, text: string) => Promise<void>;
  onRecap: (turnId: string) => Promise<string>;
}) {
  const [editing, setEditing] = React.useState(false);
  const [draft, setDraft] = React.useState(turn.answer);
  const [saving, setSaving] = React.useState(false);
  const [recap, setRecap] = React.useState<string | null>(null);
  const [recapPending, setRecapPending] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [answerModalOpen, setAnswerModalOpen] = React.useState(false);
  const longAnswer = isLongAnswer(turn.answer);
  // Guards against the interview flipping to complete (e.g. "Mark complete" in another tab)
  // while this row's textarea happens to be open — snaps back to the read-only row on the next
  // render rather than leaving a save affordance up for a write the server will now refuse.
  const showEditor = editing && editable;

  async function save() {
    setSaving(true);
    setError(null);
    try {
      await onEdit(turn.id, draft);
      setEditing(false);
      setRecap(null); // stale over the old answer — never shown as if it matched the new one
    } catch (e) {
      setError(e instanceof Error ? e.message : "couldn't save that edit");
    } finally {
      setSaving(false);
    }
  }

  async function toggleRecap() {
    if (recap !== null) {
      setRecap(null);
      return;
    }
    setRecapPending(true);
    setError(null);
    try {
      setRecap(await onRecap(turn.id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "couldn't generate a recap");
    } finally {
      setRecapPending(false);
    }
  }

  return (
    <li className="rounded-md border px-3 py-2 text-sm">
      <div className="text-[10px] uppercase text-muted-foreground">
        {personaLabel(turn.persona)}
      </div>
      <div className="mt-0.5 text-xs text-muted-foreground">{turn.question}</div>

      {showEditor ? (
        <div className="mt-1.5 flex flex-col gap-2">
          <TextArea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            className="min-h-16 px-2 py-1.5"
          />
          <div className="flex gap-2">
            <Button size="sm" onClick={save} disabled={saving || !draft.trim()}>
              {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden /> : null}
              Save
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                setDraft(turn.answer);
                setEditing(false);
              }}
              disabled={saving}
            >
              Cancel
            </Button>
          </div>
        </div>
      ) : (
        <div className="mt-1 flex items-start justify-between gap-2">
          <p className={cn("min-w-0 flex-1", longAnswer && "line-clamp-3")}>{turn.answer}</p>
          <div className="flex shrink-0 gap-1">
            {longAnswer ? (
              <Button size="sm" variant="ghost" onClick={() => setAnswerModalOpen(true)}>
                Full answer
              </Button>
            ) : null}
            <Button size="sm" variant="ghost" onClick={toggleRecap} disabled={recapPending}>
              {recapPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden /> : null}
              Recap
            </Button>
            {editable ? (
              <Button size="sm" variant="ghost" onClick={() => setEditing(true)}>
                Edit
              </Button>
            ) : null}
          </div>
        </div>
      )}

      {longAnswer ? (
        <Modal
          open={answerModalOpen}
          onOpenChange={setAnswerModalOpen}
          title={`${personaLabel(turn.persona)} — full answer`}
          description={turn.question}
        >
          <p className="whitespace-pre-wrap text-sm">{turn.answer}</p>
        </Modal>
      ) : null}

      {recap !== null && !showEditor ? (
        <div className="mt-1.5 rounded-md border border-dashed bg-muted/20 px-2.5 py-1.5 text-xs">
          <div className="text-[10px] uppercase text-muted-foreground">here&rsquo;s what I heard</div>
          {recap}
        </div>
      ) : null}

      {error ? <Alert className="mt-1 text-xs">{error}</Alert> : null}
    </li>
  );
}
