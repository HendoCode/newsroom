"use client";

import * as React from "react";
import Link from "next/link";
import { Edit, Loader2 } from "lucide-react";

import { ArchiveToggle } from "@/components/piece-detail/archive-toggle";
import { AtAGlance } from "@/components/piece-detail/at-a-glance";
import { ActivityLog } from "@/components/piece-detail/activity-log";
import { SeededDataBadge } from "@/components/dashboard/seeded-data-badge";
import { BetweenRoundsLog } from "@/components/piece-detail/between-rounds-log";
import { CouncilRecord } from "@/components/piece-detail/council-record";
import { DraftView } from "@/components/piece-detail/draft-view";
import { Pipeline } from "@/components/piece-detail/pipeline";
import {
  isPostPublish,
  PostPublishWorkspace,
} from "@/components/piece-detail/post-publish-workspace";
import { ReviewRoundSummary } from "@/components/piece-detail/review-round-summary";
import { StatusFacets } from "@/components/piece-detail/status-facets";
import { TranscriptRecord } from "@/components/piece-detail/transcript-record";
import { NarrativeReveal } from "@/components/spikes/narrative-reveal";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CollapsibleSection } from "@/components/ui/collapsible-section";
import { relativeTime } from "@/lib/format/relative-time";
import { humanTouchStaleness } from "@/lib/format/staleness";
import type { TranscriptTurn } from "@/lib/interviews/types";
import type { PieceDetail } from "@/lib/pieces/types";
import { cn } from "@/lib/utils";

/**
 * The piece-detail screen (cmw-ui-wireframes screen 2 + cmw-pipeline-depiction-design): header,
 * the unified `Pipeline` block (rail + stage-contextual CTA + failure/decision state, see that
 * component's doc), a split body (semantic draft + editorial block / council record / interview
 * transcript on the left; at-a-glance and the activity/between-rounds logs on the right).
 * Post-publish, a tablist (Outputs / Derivatives) sits between the Pipeline and that body so
 * ship is no longer the last beat in the IA (cmw-repurposing-derivatives-ia).
 *
 * Holds the piece as client state so firing a trigger (inside `Pipeline`) can refresh the whole
 * screen in place — a batch chain (e.g. drafting → council → review) can advance several stages in
 * one call, so a full refetch after the POST is simpler and more honest than patching fields.
 *
 * **Collapsible-by-default (cmw-piece-detail-collapsible)**: this page accumulated a Card per task
 * (draft, council, transcript, at-a-glance, two audit logs, a static reference table) — fine one
 * at a time, unscannable stacked. The Pipeline block never gets a collapse control at all (the
 * page's one hard requirement: current stage + next action must be obvious with nothing
 * expanded — its own internal stage→action reference sub-section is the one exception, since
 * collapsing that never hides the rail or the CTA themselves); At a glance stays open too
 * (cheap to show fully, still bears on deciding the next move). Published outputs move into the
 * post-publish tablist, next to Derivatives, rather than living as an always-open right-column
 * card — post-publish is a different mode, not more of the in-flight inspector. Everything else —
 * Council record, Interview transcript, and both logs — defaults collapsed via the shared
 * `CollapsibleSection` (components/ui/collapsible-section.tsx, PR #89's `ExpandToggle` idiom
 * generalized from a list row to a whole Card), each with a `summary` that keeps its headline
 * fact scannable even collapsed. `DraftView` is always expanded on landing when content exists
 * (cmw-piece-draft-visibility) — length only clamps the body, never hides it behind a collapsed card.
 */
export function PieceDetailView({
  initial,
  initialTurns,
  interviewerPersonas = [],
  originNarrativeId = null,
}: {
  initial: PieceDetail;
  initialTurns: TranscriptTurn[];
  /** The interviewer persona roster — only consumed by `Pipeline`'s review-stage "Start another
   * round of interviews" action. Defaults to empty so every existing caller/test stays valid
   * without threading it through. */
  interviewerPersonas?: string[];
  /** The narrative id behind this piece's origin spike (resolved server-side in `page.tsx` via
   * `piece.origin_spike_id` → `fetchSpike` → `spike.origin.ref`, only when
   * `spike.origin.kind === "narrative"`) — `null` for a piece with no origin spike, an origin
   * spike from something other than a spoken narrative, or an unreachable spike. Reuses the same
   * `NarrativeReveal` component the spike-kickoff screen already uses; no parallel fetch path. */
  originNarrativeId?: string | null;
}) {
  const [piece, setPiece] = React.useState(initial);
  // Captured once on mount (client-only) so server- and client-rendered relative timestamps in the
  // activity log match — the same pattern the dashboard uses for its date-filter clock.
  const now = React.useMemo(() => new Date(), []);
  const [renaming, setRenaming] = React.useState(false);

  async function handleRename() {
    const newTitle = window.prompt("Rename piece", piece.title || "");
    if (newTitle === null) return; // cancelled
    if (newTitle === piece.title) return; // unchanged
    setRenaming(true);
    try {
      const res = await fetch(`/api/pieces/${encodeURIComponent(piece.id)}/title`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: newTitle }),
      });
      if (!res.ok) {
        throw new Error(`Failed to rename piece: ${res.statusText}`);
      }
      const data = await res.json();
      setPiece((prev) => ({ ...prev, title: data.title }));
    } finally {
      setRenaming(false);
    }
  }

  // Even collapsed, the transcript section keeps a "Resume interview" link pinned in view when
  // one is actually open — the same "must not miss an actionable control" rule the failures
  // banner and the draft's editorial block below both follow.
  const openInterview = piece.interviews.find((i) => i.status === "open") ?? null;
  const latestActivity = piece.activity[0] ?? null;

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <Button asChild variant="ghost" size="sm" className="mb-2 -ml-2">
            <Link href="/newsroom">&larr; Back to dashboard</Link>
          </Button>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="font-serif text-3xl font-semibold">{piece.title}</h1>
            <Button
              variant="ghost"
              size="icon"
              onClick={handleRename}
              disabled={renaming}
              title="Rename piece"
              className="h-8 w-8"
            >
              {renaming ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
              ) : (
                <Edit className="h-4 w-4" aria-hidden />
              )}
            </Button>
            {piece.brain_synced ? (
              <Badge
                variant="outline"
                title="Registered from a brain-authored drafts/ folder (never went through the interview → draft → council pipeline); its content reads straight from the brain"
              >
                Brain draft
              </Badge>
            ) : null}
            {piece.archived_at ? (
              <Badge variant="muted" title="Hidden from the dashboard queue only">
                Archived
              </Badge>
            ) : null}
            {/* Placeholder provenance survives the click-through from a seeded list
                (cmw-boss-facing-presentation, HIGH); the "how do I make this real?" link is
                part of the badge itself. */}
            {piece.seeded ? <SeededDataBadge seeded /> : null}
            <ReviewRoundSummary piece={piece} />
          </div>
          {/* The piece's status as six separate facets (stage / execution / review / attention /
              lineage / learning) instead of one flattened stage badge — each opens its own
              detail drawer (components/piece-detail/status-facets.tsx). */}
          <div className="mt-2">
            <StatusFacets piece={piece} />
          </div>
          <p className="mt-1 text-sm text-muted-foreground">
            voice <b className="text-foreground">{piece.voice}</b>
            {piece.owner ? (
              <>
                {" · "}owner <b className="text-foreground">{piece.owner}</b>
              </>
            ) : null}
            {piece.origin_spike_id ? (
              <>
                {" · "}source spike <span className="font-mono">{piece.origin_spike_id}</span>
              </>
            ) : null}
            {piece.target ? <> · target: {piece.target}</> : null}
            {piece.parent_piece_id ? (
              <>
                {" · "}
                <Link href={`/pieces/${encodeURIComponent(piece.parent_piece_id)}`} className="underline">
                  derived from the main piece
                </Link>
              </>
            ) : null}
            {/* Staleness triage (cmw-staleness-timestamps): `updated` is "any write, including a
                machine-only batch job"; `last action` is "a person actually acted on this" — never
                conflate the two, or the field lies about a job completion being a human touch.
                Each fact is its own `<span>` (unlike the plain-text facts above) so it renders as
                a discrete, queryable unit — matching the dashboard card's identical facts. */}
            {piece.updated_at ? (
              <>
                {" · "}
                <span title="Last write of any kind, including a background job">
                  updated{" "}
                  <b className="text-foreground">{relativeTime(piece.updated_at, now)}</b>
                </span>
              </>
            ) : null}
            {" · "}
            <span title="Last time a person acted on this piece (a stage trigger, or an interview answer/edit)">
              last action{" "}
              <b
                className={cn(
                  humanTouchStaleness(piece.last_human_touch_at, now) === "fresh"
                    ? "text-foreground"
                    : "text-warning",
                )}
              >
                {piece.last_human_touch_at ? relativeTime(piece.last_human_touch_at, now) : "never"}
              </b>
            </span>
          </p>
          {originNarrativeId ? (
            <div className="mt-2">
              <NarrativeReveal
                narrativeId={originNarrativeId}
                subject="the narrative that started this piece"
              />
            </div>
          ) : null}
        </div>
        <ArchiveToggle piece={piece} onUpdated={setPiece} />
      </div>

      {/* The Pipeline block is the one thing this whole page exists to answer — "what stage is
          this at, what do I do next" (rail + CTA + any failure/decision state, all one block per
          cmw-pipeline-depiction-design) — so it never gets a collapse control; everything else on
          this page defaults collapsed or adapts to content size (see each section below), never
          the other way round. */}
      <Pipeline piece={piece} onUpdated={setPiece} interviewerPersonas={interviewerPersonas} />

      {isPostPublish(piece) ? <PostPublishWorkspace piece={piece} /> : null}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="flex min-w-0 flex-col gap-6">
          {/* DraftView owns its own CollapsibleSection. Content that exists is always shown on
              landing (clamped if long) — collapsing it hid the piece itself. */}
          <DraftView
            draftHtml={piece.draft_html}
            revision={piece.latest_revision}
            sources={piece.evidence_sources ?? []}
            citations={piece.evidence_citations ?? []}
            brainSynced={piece.brain_synced}
          />

          <CollapsibleSection
            title="Council record"
            empty={piece.council === null}
            summary={
              piece.council ? (
                <span>
                  aggregate <b className="text-foreground">{piece.council.aggregate?.toFixed(1) ?? "—"}</b>
                  {" · round "}
                  {piece.council.round_number}
                  {piece.council.iteration > 1 ? <> · iteration {piece.council.iteration}</> : null}
                  {piece.council.stop_reason ? <> · {piece.council.stop_reason.replace(/_/g, " ")}</> : null}
                </span>
              ) : null
            }
          >
            <CouncilRecord council={piece.council} />
          </CollapsibleSection>

          <CollapsibleSection
            title="Interview transcript"
            empty={piece.interviews.length === 0 && initialTurns.length === 0}
            summary={
              piece.interviews.length > 0 || initialTurns.length > 0 ? (
                <span>
                  {piece.interviews.length} round{piece.interviews.length === 1 ? "" : "s"} &middot;{" "}
                  {initialTurns.length} turn{initialTurns.length === 1 ? "" : "s"}
                </span>
              ) : null
            }
            pinned={
              openInterview ? (
                <Button asChild size="sm" variant="secondary">
                  <Link href={`/interviews/${openInterview.interview_id}`}>Resume interview</Link>
                </Button>
              ) : undefined
            }
          >
            <TranscriptRecord
              interviews={piece.interviews}
              turns={initialTurns}
              originSpikeId={piece.origin_spike_id}
            />
          </CollapsibleSection>
        </div>

        <div className="flex min-w-0 flex-col gap-6">
          {/* At a glance stays open by default too — it's the compact GAP/clearance/cost readout
              that's cheap to show fully and, unlike the sections below, still bears on deciding
              the next move (e.g. is it safe to finalize with open GAPs?). */}
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">At a glance</CardTitle>
            </CardHeader>
            <CardContent>
              <AtAGlance piece={piece} />
            </CardContent>
          </Card>

          {/* Everything below is reference/history — useful when drilling in, never needed to
              answer "what's next" — so it collapses by default (Hendo: collapsible elements that
              start that way), with a summary line that keeps the headline fact scannable anyway.
              The stage → primary action reference now lives inside the Pipeline block itself
              (its own collapsed-by-default sub-section), not as a separate card here. */}
          <CollapsibleSection
            title="Activity / routing log"
            empty={piece.activity.length === 0}
            summary={
              latestActivity ? (
                <span>
                  {piece.activity.length} entr{piece.activity.length === 1 ? "y" : "ies"} &middot; latest:{" "}
                  {latestActivity.label}
                </span>
              ) : null
            }
          >
            <ActivityLog entries={piece.activity} now={now} />
          </CollapsibleSection>

          <CollapsibleSection
            title="Between-rounds routing log"
            empty={piece.review_rounds.length === 0}
            summary={
              piece.review_rounds.length > 0
                ? `${piece.review_rounds.length} round${piece.review_rounds.length === 1 ? "" : "s"}`
                : null
            }
          >
            <BetweenRoundsLog rounds={piece.review_rounds} />
          </CollapsibleSection>
        </div>
      </div>
    </div>
  );
}
