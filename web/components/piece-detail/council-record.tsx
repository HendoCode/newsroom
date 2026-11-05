"use client";

import * as React from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Modal } from "@/components/ui/modal";
import type { CouncilRecord as CouncilRecordData, EditorScore } from "@/lib/pieces/types";

/** The council record table (domain model §1.13): mandatory editors flagged, per-editor score and
 * fix/gap/clearance notes, the aggregate, iteration, and stop reason. */
export function CouncilRecord({ council }: { council: CouncilRecordData | null }) {
  if (!council) {
    return (
      <div className="rounded-lg border border-dashed bg-muted/30 p-6 text-center text-sm text-muted-foreground">
        No council pass yet — it runs once drafting completes.
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-left text-muted-foreground">
            <th className="py-1.5 pr-3 font-medium">Editor</th>
            <th className="py-1.5 pr-3 font-medium">Score</th>
            <th className="py-1.5 pr-3 font-medium">Notes</th>
          </tr>
        </thead>
        <tbody>
          {council.editor_scores.map((score) => (
            <tr key={score.editor} className="border-b last:border-0">
              <td className="py-1.5 pr-3 align-top">
                <span className="flex flex-wrap items-center gap-1.5">
                  {score.editor}
                  {score.mandatory ? <Badge variant="muted">mandatory</Badge> : null}
                  {score.hard_cap_applied ? <Badge variant="warning">hard cap</Badge> : null}
                </span>
              </td>
              <td className="py-1.5 pr-3 align-top font-mono">{score.score.toFixed(1)}</td>
              <td className="py-1.5 pr-3 align-top text-muted-foreground">
                <EditorNotes score={score} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="text-sm text-muted-foreground">
        Aggregate{" "}
        <b className="text-foreground">{council.aggregate != null ? council.aggregate.toFixed(1) : "—"}</b>
        {" · "}round {council.round_number}
        {council.iteration > 1 ? <span> · iteration {council.iteration}</span> : null}
        {council.stop_reason ? (
          <span>
            {" · "}stopped: <b className="text-foreground">{council.stop_reason.replace(/_/g, " ")}</b>
            {council.stop_message ? (
              <span className="text-muted-foreground"> — {council.stop_message}</span>
            ) : null}
          </span>
        ) : null}
      </p>
    </div>
  );
}

interface NoteItem {
  kind: "Fix" | "Gap" | "Clearance";
  text: string;
}

// A council editor's fix/gap notes are free-form Opus output (app/orchestration/council_step.py's
// _JSON_CONTRACT: "specific, actionable textual fixes" / "facts only the author can supply") —
// unlike a review round's routing-log lines (capped at a short template + an 80-char preview),
// these have no length ceiling and an editor can return several. Show the first two inline (never
// hidden by default — PR #91's "anything a user must not miss stays visible" rule, and a note is
// exactly the kind of thing a piece owner shouldn't have to click to discover exists), and only
// reach for the modal once there's genuinely more than that to read.
const NOTES_PREVIEW_ITEMS = 2;

function toNoteItems(score: EditorScore): NoteItem[] {
  return [
    ...score.editorial_fixes.map((text): NoteItem => ({ kind: "Fix", text })),
    ...score.information_gaps.map((text): NoteItem => ({ kind: "Gap", text })),
    ...(score.clearances ?? []).map((text): NoteItem => ({ kind: "Clearance", text })),
  ];
}

/** Renders an editor's fix/gap notes — up to `NOTES_PREVIEW_ITEMS` inline, each clamped to one
 * line, with a "View all notes" `Modal` (the same reusable long-form dialog `DraftView` uses) once
 * there's more than that to show. */
function EditorNotes({ score }: { score: EditorScore }) {
  const [open, setOpen] = React.useState(false);
  const items = toNoteItems(score);

  if (items.length === 0) {
    return <span>—</span>;
  }

  const hasMore = items.length > NOTES_PREVIEW_ITEMS;
  const preview = hasMore ? items.slice(0, NOTES_PREVIEW_ITEMS) : items;

  return (
    <div className="flex flex-col gap-1">
      <NoteList items={preview} clampLines />
      {hasMore ? (
        <>
          <Button
            variant="ghost"
            size="sm"
            className="h-6 w-fit px-1.5 text-xs"
            onClick={() => setOpen(true)}
          >
            View all {items.length} notes
          </Button>
          <Modal open={open} onOpenChange={setOpen} title={`${score.editor} — fix & gap notes`}>
            <NoteList items={items} clampLines={false} />
          </Modal>
        </>
      ) : null}
    </div>
  );
}

function NoteList({ items, clampLines }: { items: NoteItem[]; clampLines: boolean }) {
  return (
    <ul className="flex flex-col gap-1 text-sm">
      {items.map((item, index) => (
        <li key={index} className="flex items-start gap-1.5">
          <Badge variant={item.kind === "Fix" ? "muted" : item.kind === "Clearance" ? "warning" : "warning"} className="mt-0.5 shrink-0">
            {item.kind}
          </Badge>
          <span className={clampLines ? "line-clamp-1" : undefined}>{item.text}</span>
        </li>
      ))}
    </ul>
  );
}
