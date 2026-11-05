"use client";

import * as React from "react";
import Link from "next/link";

import { CouncilRecord } from "@/components/piece-detail/council-record";
import { Badge } from "@/components/ui/badge";
import { Modal } from "@/components/ui/modal";
import {
  attentionState,
  executionState,
  FACET_LABELS,
  facetSummaries,
  learningState,
  type FacetKind,
  type FacetSummary,
  type FacetTone,
} from "@/lib/pieces/facets";
import { relativeTime } from "@/lib/format/relative-time";
import type { PieceDetail } from "@/lib/pieces/types";
import { cn } from "@/lib/utils";

/**
 * The piece's status as SIX separate facets — stage, execution, review, attention, lineage,
 * learning — instead of one flattened status badge (v1 launch wave, "ui-state-facets"). The
 * strip replaces the header's single `StageBadge`: the stage facet is the first badge (same
 * visual continuity), and the other five carry the facts a single stage label always hid —
 * e.g. a piece in `review` that also has a failed job behind it and three lessons pending.
 *
 * Each facet is a badge-button; clicking any of them opens that facet's drawer (`Modal`, the
 * app's one overlay primitive) with the full detail behind the compact read-out. Derivation is
 * pure and lives in `lib/pieces/facets.ts` (unit-tested there); this component only renders.
 */

const TONE_CLASSES: Record<FacetTone, string> = {
  // Semantic badge variants only (components/ui/badge.tsx) — never hard-coded color.
  neutral: "border-transparent bg-secondary text-secondary-foreground",
  active: "border-border text-foreground",
  warning: "border-transparent bg-warning/15 text-warning",
  success: "border-transparent bg-muted text-foreground",
};

export function StatusFacets({ piece }: { piece: PieceDetail }) {
  const [openFacet, setOpenFacet] = React.useState<FacetKind | null>(null);
  const summaries = facetSummaries(piece);
  const open = openFacet !== null;

  return (
    <div
      role="group"
      aria-label="Piece status facets"
      className="flex flex-wrap items-center gap-1.5"
    >
      {summaries.map((facet) => (
        <FacetBadge key={facet.kind} facet={facet} onOpen={() => setOpenFacet(facet.kind)} />
      ))}
      <Modal
        open={open}
        onOpenChange={(next) => setOpenFacet(next ? openFacet : null)}
        title={openFacet ? `${FACET_LABELS[openFacet]} — ${piece.title}` : ""}
        description={openFacet ? FACET_DESCRIPTIONS[openFacet] : undefined}
      >
        {openFacet ? <FacetDetail kind={openFacet} piece={piece} /> : null}
      </Modal>
    </div>
  );
}

function FacetBadge({ facet, onOpen }: { facet: FacetSummary; onOpen: () => void }) {
  return (
    <button
      type="button"
      onClick={onOpen}
      aria-haspopup="dialog"
      title={`${facet.label} — open details`}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-xs font-medium transition-colors",
        "hover:opacity-80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        TONE_CLASSES[facet.tone],
      )}
    >
      <span className="uppercase tracking-wide opacity-70">{facet.label}</span>
      <span data-testid={`facet-value-${facet.kind}`}>{facet.value}</span>
    </button>
  );
}

const FACET_DESCRIPTIONS: Record<FacetKind, string> = {
  stage: "Where this piece sits in the pipeline — one of the nine settled states.",
  execution: "The machine's background work on this piece: running jobs, open failures, spend.",
  review: "Editorial quality: the council pass and any human review round in flight.",
  attention: "Everything a human still owes this piece before it can move on.",
  lineage: "Where the content came from: origin spike, revision, and provenance.",
  learning: "The lessons loop (D12): what this piece taught the voice, and what's pending.",
};

function FacetDetail({ kind, piece }: { kind: FacetKind; piece: PieceDetail }) {
  switch (kind) {
    case "stage":
      return <StageDetail piece={piece} />;
    case "execution":
      return <ExecutionDetail piece={piece} />;
    case "review":
      return <ReviewDetail piece={piece} />;
    case "attention":
      return <AttentionDetail piece={piece} />;
    case "lineage":
      return <LineageDetail piece={piece} />;
    case "learning":
      return <LearningDetail piece={piece} />;
  }
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b pb-1.5 text-sm last:border-0">
      <span className="shrink-0 text-muted-foreground">{label}</span>
      <span className="min-w-0 text-right">{children}</span>
    </div>
  );
}

function StageDetail({ piece }: { piece: PieceDetail }) {
  return (
    <div className="flex flex-col gap-2">
      <Row label="Stage">
        <b>{piece.stage}</b>
      </Row>
      {piece.review_round ? (
        <Row label="Review round">{piece.review_round.round_number}</Row>
      ) : null}
      <Row label="Voice">{piece.voice}</Row>
      {piece.archived_at ? <Row label="Archived">hidden from the dashboard queue only</Row> : null}
      <p className="mt-1 text-xs text-muted-foreground">
        The pipeline rail above shows this stage in context, with the next action. Batch stages
        (drafting / council / incorporating / finalizing) are the machine working; every other
        stage is waiting on a person.
      </p>
    </div>
  );
}

function ExecutionDetail({ piece }: { piece: PieceDetail }) {
  const exec = executionState(piece);
  return (
    <div className="flex flex-col gap-2">
      <Row label="Machine status">
        <b>{exec.status}</b>
      </Row>
      {piece.failures.length > 0 ? (
        <div className="mt-2 flex flex-col gap-2">
          <p className="text-sm font-medium">Open failures (flagged, never rolled back)</p>
          {piece.failures.map((failure, index) => (
            <div key={`${failure.type}-${index}`} className="rounded-md border border-warning/40 bg-warning/5 p-2 text-sm">
              <p>
                <b>{failure.type}</b> job · <span className="font-mono">{failure.code}</span>
                {failure.retryable ? <Badge variant="muted" className="ml-1.5">retryable</Badge> : null}
              </p>
              <p className="mt-0.5 text-muted-foreground">{failure.message}</p>
            </div>
          ))}
        </div>
      ) : (
        <p className="mt-1 text-xs text-muted-foreground">No failed or stuck jobs on this piece.</p>
      )}
    </div>
  );
}

function ReviewDetail({ piece }: { piece: PieceDetail }) {
  return (
    <div className="flex flex-col gap-3">
      <CouncilRecord council={piece.council} />
      {piece.review_round ? (
        <p className="text-sm">
          Review round <b>{piece.review_round.round_number}</b> is{" "}
          <b>{piece.review_round.status}</b> ({piece.review_round.share_mode} share).
          {piece.review_round.doc_url ? (
            <>
              {" "}
              <Link href={piece.review_round.doc_url} className="underline">
                Open the review Doc
              </Link>
            </>
          ) : null}
        </p>
      ) : (
        <p className="text-sm text-muted-foreground">No human review round opened yet.</p>
      )}
    </div>
  );
}

function AttentionDetail({ piece }: { piece: PieceDetail }) {
  const attention = attentionState(piece);
  if (attention.total === 0) {
    return (
      <p className="text-sm">
        Nothing needs a person right now — no open GAPs, no clearances, no open interview, no
        failed jobs.
      </p>
    );
  }
  const openInterview = piece.interviews.find((i) => i.status === "open") ?? null;
  return (
    <div className="flex flex-col gap-2">
      <Row label="Open GAPs (information the draft is missing)">{attention.openGaps}</Row>
      <Row label="Open clearances (permissions to name/share)">{attention.openClearances}</Row>
      <Row label="Open interviews">
        {openInterview ? (
          <Link href={`/interviews/${openInterview.interview_id}`} className="underline">
            resume{openInterview.assigned_expert ? ` (${openInterview.assigned_expert})` : ""}
          </Link>
        ) : (
          attention.openInterviews
        )}
      </Row>
      <Row label="Failed/stuck jobs">{attention.failedJobs}</Row>
      <p className="mt-1 text-xs text-muted-foreground">
        The editorial block under the draft and the failures banner above carry the detail for
        each of these.
      </p>
    </div>
  );
}

function LineageDetail({ piece }: { piece: PieceDetail }) {
  const now = new Date();
  return (
    <div className="flex flex-col gap-2">
      <Row label="Origin spike">
        {piece.origin_spike_id ? (
          <Link href={`/spikes/${piece.origin_spike_id}`} className="font-mono underline">
            {piece.origin_spike_id}
          </Link>
        ) : (
          "none recorded"
        )}
      </Row>
      <Row label="Latest revision">
        {piece.latest_revision ? (
          <span className="font-mono">{piece.latest_revision}</span>
        ) : (
          "no revision yet"
        )}
      </Row>
      <Row label="Provenance">
        {piece.brain_synced
          ? "brain-authored draft, registered by the brain sync"
          : "created through the pipeline"}
      </Row>
      {piece.created_at ? <Row label="Created">{relativeTime(piece.created_at, now)}</Row> : null}
      {piece.updated_at ? (
        <Row label="Last write of any kind">{relativeTime(piece.updated_at, now)}</Row>
      ) : null}
      {piece.last_human_touch_at ? (
        <Row label="Last human action">{relativeTime(piece.last_human_touch_at, now)}</Row>
      ) : (
        <Row label="Last human action">never</Row>
      )}
    </div>
  );
}

const LESSON_STATUS_LABELS: Record<string, string> = {
  proposed: "proposed",
  accepted: "accepted",
  rejected: "rejected",
};

function LearningDetail({ piece }: { piece: PieceDetail }) {
  const learning = learningState(piece);
  if (learning.total === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No lessons yet — the loop proposes them after the piece is finalized, once the
        published version can be diffed against the draft.
      </p>
    );
  }
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap gap-1.5">
        <Badge variant={learning.proposed > 0 ? "warning" : "muted"}>
          {learning.proposed} proposed
        </Badge>
        <Badge variant="muted">{learning.accepted} accepted</Badge>
        <Badge variant="muted">{learning.rejected} rejected</Badge>
      </div>
      <ul className="flex flex-col gap-2">
        {piece.lessons.map((lesson) => (
          <li key={lesson.id} className="rounded-md border p-2 text-sm">
            <p>{lesson.generalizable_rule}</p>
            <p className="mt-1 text-xs text-muted-foreground">
              {lesson.voice ? (
                <>
                  voice <b>{lesson.voice}</b> ·{" "}
                </>
              ) : null}
              {LESSON_STATUS_LABELS[lesson.status] ?? lesson.status}
            </p>
          </li>
        ))}
      </ul>
      {learning.proposed > 0 ? (
        <p className="text-xs text-muted-foreground">
          The machine never self-commits a lesson — accept/edit/reject lives on the voice kit&rsquo;s
          lessons gate (<Link href="/voice-kit" className="underline">open voice kit</Link>).
        </p>
      ) : null}
    </div>
  );
}
