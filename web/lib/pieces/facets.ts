/**
 * Status facets for one piece (v1 launch wave, "ui-state-facets"): six separate read-outs —
 * stage, execution, review, attention, lineage, learning — instead of one flattened status
 * badge. A piece in `review` with two open GAPs, a failed finalize job behind it and three
 * pending lessons is SIX facts, not one, and collapsing them loses exactly the information an
 * operator triages by.
 *
 * These helpers are the pure derivation half (what each facet's badge shows + which tone it
 * carries); the rendering + drawer half lives in `components/piece-detail/status-facets.tsx`.
 * Every input comes off the existing `GET /api/pieces/{id}` contract (`PieceDetail`) — no new
 * wire fields were needed for the facets themselves.
 */

import { stageLabel } from "@/lib/dashboard/actions";
import type { PieceDetail } from "@/lib/pieces/types";
import { LOOP_STAGES } from "@/lib/pieces/stage";

export type FacetKind =
  | "stage"
  | "execution"
  | "review"
  | "attention"
  | "lineage"
  | "learning";

/** The visual weight a facet badge carries — semantic tokens only (badge.tsx variants). */
export type FacetTone = "neutral" | "active" | "warning" | "success";

export interface FacetSummary {
  kind: FacetKind;
  /** The facet's own name, shown as the badge's lead label ("Stage", "Attention", …). */
  label: string;
  /** The compact read-out ("Review · 8.0", "2 open", "idle"). */
  value: string;
  tone: FacetTone;
}

export const FACET_LABELS: Record<FacetKind, string> = {
  stage: "Stage",
  execution: "Execution",
  review: "Review",
  attention: "Attention",
  lineage: "Lineage",
  learning: "Learning",
};

/** The one canonical order the facet strip renders in — lifecycle order, not alphabetical. */
export const FACET_ORDER: FacetKind[] = [
  "stage",
  "execution",
  "review",
  "attention",
  "lineage",
  "learning",
];

// The piece-detail activity log's job lines are shaped "{type} job {status}" by
// agents `app/piece_detail._job_entries` — the machine's own running/queued signal is those
// lines, not a separate field.
const RUNNING_RE = / job (queued|running)$/;

export interface ExecutionState {
  status: "failed" | "running" | "idle";
  failedJobs: number;
  running: boolean;
}

/** Execution facet: is the machine working on it, has it left an open failure, or is it idle.
 * Open failures (flag-not-rollback, domain model §1.16) outrank a running job in the read-out. */
export function executionState(piece: PieceDetail): ExecutionState {
  const running = piece.activity.some((a) => RUNNING_RE.test(a.label));
  const failedJobs = piece.failures.length;
  return {
    status: failedJobs > 0 ? "failed" : running ? "running" : "idle",
    failedJobs,
    running,
  };
}

export interface AttentionState {
  /** Everything a human still owes this piece, as one count. */
  total: number;
  openGaps: number;
  openClearances: number;
  openInterviews: number;
  failedJobs: number;
}

/** Attention facet: open GAPs + clearances + open interviews + open job failures — the four
 * "this needs a person" signals a piece carries. Zero means genuinely clear. */
export function attentionState(piece: PieceDetail): AttentionState {
  const openInterviews = piece.interviews.filter((i) => i.status === "open").length;
  const state = {
    openGaps: piece.open_gaps,
    openClearances: piece.open_clearances,
    openInterviews,
    failedJobs: piece.failures.length,
  };
  return {
    ...state,
    total: state.openGaps + state.openClearances + state.openInterviews + state.failedJobs,
  };
}

export interface LearningState {
  total: number;
  proposed: number;
  accepted: number;
  rejected: number;
}

/** Learning facet: the D12 lessons loop's state — proposed lessons are a human decision
 * (voice-kit accept/reject gate), so any pending one gives the facet its warning tone. */
export function learningState(piece: PieceDetail): LearningState {
  const counts = { proposed: 0, accepted: 0, rejected: 0 };
  for (const lesson of piece.lessons) {
    if (lesson.status in counts) counts[lesson.status] += 1;
  }
  return { total: piece.lessons.length, ...counts };
}

function stageFacet(piece: PieceDetail): FacetSummary {
  const round =
    LOOP_STAGES.has(piece.stage) && piece.review_round ? piece.review_round.round_number : null;
  return {
    kind: "stage",
    label: FACET_LABELS.stage,
    value: round ? `${stageLabel(piece.stage)} · round ${round}` : stageLabel(piece.stage),
    tone: "neutral",
  };
}

function executionFacet(piece: PieceDetail): FacetSummary {
  const exec = executionState(piece);
  const value =
    exec.status === "failed"
      ? `${exec.failedJobs} failed`
      : exec.status === "running"
        ? "running"
        : "idle";
  return {
    kind: "execution",
    label: FACET_LABELS.execution,
    value,
    tone: exec.status === "failed" ? "warning" : exec.status === "running" ? "active" : "neutral",
  };
}

function reviewFacet(piece: PieceDetail): FacetSummary {
  if (!piece.council) {
    return { kind: "review", label: FACET_LABELS.review, value: "no council yet", tone: "neutral" };
  }
  const aggregate =
    piece.council.aggregate !== null ? piece.council.aggregate.toFixed(1) : "unscored";
  return {
    kind: "review",
    label: FACET_LABELS.review,
    value: `${aggregate} · r${piece.council.round_number}`,
    tone: "success",
  };
}

function attentionFacet(piece: PieceDetail): FacetSummary {
  const attention = attentionState(piece);
  return {
    kind: "attention",
    label: FACET_LABELS.attention,
    value: attention.total === 0 ? "clear" : `${attention.total} open`,
    tone: attention.total === 0 ? "success" : "warning",
  };
}

function lineageFacet(piece: PieceDetail): FacetSummary {
  const rev = piece.latest_revision
    ? `rev ${piece.latest_revision.slice(0, 7)}`
    : "no revision";
  const origin = piece.origin_spike_id ? " · from spike" : "";
  return {
    kind: "lineage",
    label: FACET_LABELS.lineage,
    value: `${rev}${origin}${piece.brain_synced ? " · brain draft" : ""}`,
    tone: "neutral",
  };
}

function learningFacet(piece: PieceDetail): FacetSummary {
  const learning = learningState(piece);
  if (learning.total === 0) {
    return { kind: "learning", label: FACET_LABELS.learning, value: "none yet", tone: "neutral" };
  }
  return {
    kind: "learning",
    label: FACET_LABELS.learning,
    value:
      learning.proposed > 0
        ? `${learning.proposed} to decide`
        : `${learning.accepted} accepted`,
    tone: learning.proposed > 0 ? "warning" : "neutral",
  };
}

/** All six facet summaries, in the canonical strip order. */
export function facetSummaries(piece: PieceDetail): FacetSummary[] {
  const byKind: Record<FacetKind, FacetSummary> = {
    stage: stageFacet(piece),
    execution: executionFacet(piece),
    review: reviewFacet(piece),
    attention: attentionFacet(piece),
    lineage: lineageFacet(piece),
    learning: learningFacet(piece),
  };
  return FACET_ORDER.map((kind) => byKind[kind]);
}
