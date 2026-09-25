"use client";

import * as React from "react";
import { Loader2 } from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { defaultInterviewerSelection } from "@/lib/spikes/kickoff";
import type { PieceDetail } from "@/lib/pieces/types";

async function readErrorMessage(res: Response, fallback: string): Promise<string> {
  const body: unknown = await res.json().catch(() => null);
  if (body && typeof body === "object" && "error" in body) {
    return String((body as { error: unknown }).error);
  }
  return fallback;
}

/**
 * The form behind "Start another round of interviews" (review's secondary action,
 * `lib/pieces/actions.ts`) — Hendo's settled entry point for D16a's info-gap re-interview edge
 * (`route_to_interview`, legal only from council/review). Two real calls, in this order:
 *
 * 1. `POST /api/pieces/{id}/interviews` — opens a NEW Interview session (this round's own
 *    persona/expert/about, `is_gap_interview: true`: a human-invoked re-interview is the same
 *    "more input needed" case that a council-spawned one is, D16a). Done first, not second, so a
 *    failure of step 2 never leaves the piece stuck in `interviewing` with no open interview and
 *    no surviving control to open one (this form only renders while the piece is in `review`).
 * 2. `POST /api/pieces/{id}/trigger` firing `route-to-interview` — the actual review → interviewing
 *    stage move. A failure here is surfaced but non-fatal to the interview already opened in
 *    step 1: it's real and answerable even if the piece itself is still shown at `review`.
 *
 * Either way, the piece is refetched so the new round shows up in the transcript record above.
 */
export function OpenInterviewRoundForm({
  pieceId,
  personas,
  roundNumber,
  onUpdated,
}: {
  pieceId: string;
  personas: string[];
  roundNumber: number;
  onUpdated: (next: PieceDetail) => void;
}) {
  const [selected, setSelected] = React.useState<string[]>(() =>
    defaultInterviewerSelection(personas),
  );
  const [assignedExpert, setAssignedExpert] = React.useState("");
  const [about, setAbout] = React.useState("");
  const [submitting, setSubmitting] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [openedInterviewId, setOpenedInterviewId] = React.useState<string | null>(null);

  function togglePersona(name: string) {
    setSelected((prev) => (prev.includes(name) ? prev.filter((p) => p !== name) : [...prev, name]));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const openRes = await fetch(`/api/pieces/${encodeURIComponent(pieceId)}/interviews`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          interviewer_personas: selected,
          assigned_expert: assignedExpert || null,
          about: about || null,
          is_gap_interview: true,
        }),
      });
      if (!openRes.ok) {
        throw new Error(await readErrorMessage(openRes, "could not open a new interview"));
      }
      const created = (await openRes.json()) as { id: string };
      setOpenedInterviewId(created.id);

      const routeRes = await fetch(`/api/pieces/${encodeURIComponent(pieceId)}/trigger`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ trigger: "route-to-interview" }),
      });
      if (!routeRes.ok) {
        setError(
          `Round ${roundNumber} opened, but the piece could not be routed back to interviewing: ` +
            `${await readErrorMessage(routeRes, `request failed (${routeRes.status})`)}. The new ` +
            "interview above is still real and answerable — retry routing from here, or resume it " +
            "directly.",
        );
      }

      const refreshed = await fetch(`/api/pieces/${encodeURIComponent(pieceId)}`, {
        cache: "no-store",
      });
      if (refreshed.ok) {
        onUpdated((await refreshed.json()) as PieceDetail);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "something went wrong");
    } finally {
      setSubmitting(false);
    }
  }

  // Once the interview itself exists, never re-render the form — resubmitting it would open a
  // second, duplicate Interview for the same round. A routing failure (below) is shown alongside
  // this success block instead, never in place of it.
  if (openedInterviewId) {
    return (
      <div className="flex flex-col gap-2">
        <div className="rounded-md border bg-muted/30 px-3 py-2 text-sm">
          Round {roundNumber} opened —{" "}
          <a href={`/interviews/${openedInterviewId}`} className="underline">
            open the interview
          </a>
          .
        </div>
        {error ? <Alert>{error}</Alert> : null}
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-3 rounded-md border px-3 py-3">
      <p className="text-xs text-muted-foreground">
        Opens interview round {roundNumber}. Every earlier round&rsquo;s transcript turns stay
        intact in the one shared transcript — nothing here replaces or hides them.
      </p>
      <div className="flex flex-wrap gap-2">
        {personas.length === 0 ? (
          <span className="text-sm text-muted-foreground">no interviewer personas available</span>
        ) : null}
        {personas.map((name) => {
          const on = selected.includes(name);
          return (
            <Button
              key={name}
              type="button"
              size="sm"
              variant={on ? "default" : "outline"}
              disabled={submitting}
              onClick={() => togglePersona(name)}
              aria-pressed={on}
              className="h-auto rounded-full px-3 py-1 text-xs"
            >
              {name}
            </Button>
          );
        })}
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="flex flex-col gap-1 text-sm" htmlFor="round-expert">
          <span className="font-medium">Assigned expert (optional)</span>
          <Input
            id="round-expert"
            type="email"
            value={assignedExpert}
            onChange={(e) => setAssignedExpert(e.target.value)}
            placeholder="demo-mira@company.com"
            disabled={submitting}
          />
        </label>
        <label className="flex flex-col gap-1 text-sm" htmlFor="round-about">
          <span className="font-medium">What this round is about (optional)</span>
          <Input
            id="round-about"
            value={about}
            onChange={(e) => setAbout(e.target.value)}
            disabled={submitting}
          />
        </label>
      </div>
      <Button type="submit" disabled={submitting || selected.length === 0}>
        {submitting ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : null}
        {submitting ? "Opening…" : `Open round ${roundNumber}`}
      </Button>
      {error ? <Alert>{error}</Alert> : null}
    </form>
  );
}
