"use client";

import * as React from "react";
import { Loader2 } from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { TextArea } from "@/components/ui/textarea";
import type { PieceDetail } from "@/lib/pieces/types";

/**
 * The lessons loop's missing first step (D12; domain model §1.18): diffs the machine's final draft
 * against what was actually published and proposes generalizable per-voice lessons (Opus) — a
 * human then accepts/edits/rejects each one on the voice kit's lessons gate before "Finish
 * lessons" closes the loop. Gets its own form (rather than the generic blind trigger fire) because
 * the propose call needs a real body — the pasted published text — the same "needs configuration
 * before firing" precedent as review-round's mint panel and finalize's format selection.
 *
 * This is an LLM call, so it isn't instant: the button shows a spinner + "Proposing…" and stays
 * disabled for the duration; a failure leaves the pasted text in place (re-pasting a full article
 * would be a real cost) and surfaces the real agents-service error inline, matching the
 * accept/reject lessons gate's error convention.
 */
export function ProposeLessonsForm({
  pieceId,
  onUpdated,
}: {
  pieceId: string;
  onUpdated: (next: PieceDetail) => void;
}) {
  const [publishedContent, setPublishedContent] = React.useState("");
  const [submitting, setSubmitting] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [proposedCount, setProposedCount] = React.useState<number | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    setProposedCount(null);
    try {
      const res = await fetch(`/api/pieces/${encodeURIComponent(pieceId)}/lessons/propose`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ published_content: publishedContent }),
      });
      const body = (await res.json().catch(() => null)) as
        | { proposed?: unknown[]; error?: string }
        | null;
      if (!res.ok) {
        throw new Error(body?.error ?? `request failed (${res.status})`);
      }

      const refreshed = await fetch(`/api/pieces/${encodeURIComponent(pieceId)}`, {
        cache: "no-store",
      });
      if (refreshed.ok) {
        onUpdated((await refreshed.json()) as PieceDetail);
      }
      setProposedCount(Array.isArray(body?.proposed) ? body.proposed.length : 0);
      setPublishedContent("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "something went wrong");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="flex flex-col gap-3" onSubmit={handleSubmit}>
      <label htmlFor="published-content" className="text-sm font-medium">
        What was actually published
      </label>
      <TextArea
        id="published-content"
        value={publishedContent}
        onChange={(e) => setPublishedContent(e.target.value)}
        placeholder="Paste the final published text — diffed against the machine's own final draft to find what changed"
        rows={6}
        disabled={submitting}
        required
      />
      <Button type="submit" className="w-full" disabled={submitting || !publishedContent.trim()}>
        {submitting ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : null}
        {submitting ? "Proposing…" : "Propose lessons"}
      </Button>

      {error ? (
        <Alert>{error}</Alert>
      ) : null}
      {proposedCount !== null ? (
        <p role="status" className="text-sm text-muted-foreground">
          {proposedCount === 0
            ? "No meaningful difference found — nothing proposed."
            : `${proposedCount} lesson${proposedCount === 1 ? "" : "s"} proposed — review them on the voice kit's lessons gate.`}
        </p>
      ) : null}
    </form>
  );
}
