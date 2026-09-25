"use client";

import * as React from "react";
import Link from "next/link";
import { AlertTriangle, CheckCircle2, CircleDot, Cog, Loader2, PauseCircle, Repeat } from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ExpandToggle } from "@/components/ui/expand-toggle";
import { OpenInterviewRoundForm } from "@/components/piece-detail/open-interview-round-form";
import { ProposeLessonsForm } from "@/components/piece-detail/propose-lessons-form";
import { StageActionReference } from "@/components/piece-detail/stage-action-reference";
import { stageLabel } from "@/lib/dashboard/actions";
import { nextAction, secondaryActions } from "@/lib/pieces/actions";
import {
  isBatchStage,
  railStepStates,
  stagesInCluster,
  type RailStage,
  type RailStepState,
} from "@/lib/pieces/stage";
import type { PieceDetail, PieceStage } from "@/lib/pieces/types";
import { cn } from "@/lib/utils";

/**
 * The unified Pipeline block (cmw-pipeline-depiction-design): the one place a piece's lifecycle,
 * its stage-contextual call to action, and any failure/decision state are drawn — replacing the
 * separate Lifecycle rail, Next-action card, top-of-page failure banner, and Stage→action
 * reference card that used to each render `Piece.stage` independently with no cross-reference
 * (report's inventory: seven renderings of one field). The rail and the CTA below it never gain a
 * collapse control (the page's one hard requirement — current stage + next action must be obvious
 * with nothing expanded); only the reference table nested inside collapses, via the same
 * `ExpandToggle` idiom every other list/detail affordance in this app already uses.
 *
 * `tone` (`pipelineTone`) is the single signal driving BOTH the current rail node's styling and
 * the CTA row's icon/ring color, so the two halves of this block always agree about *why* the
 * piece is where it is — running batch job, a failure flagged it back, an interactive step
 * awaiting a human decision, or just the ordinary next step.
 */

type Tone = "default" | "running" | "warning" | "accent";

function pipelineTone(piece: PieceDetail): Tone {
  // A failure dominates regardless of stage (flag-not-rollback: the piece's current stage IS the
  // flagged-back stage) — matches the old top-of-page banner's own priority.
  if (piece.failures.length > 0) return "warning";
  if (piece.stage === "paused") return "warning";
  if (isBatchStage(piece.stage)) return "running";
  // Review and finalized both always need a human decision (mint/preview/confirm a round; publish
  // is terminal) regardless of round number or lesson count — those add detail, not urgency.
  if (piece.stage === "review" || piece.stage === "finalized") return "accent";
  if (piece.stage === "lessons") {
    return piece.lessons.some((l) => l.status === "proposed") ? "accent" : "default";
  }
  return "default";
}

const CURRENT_RING: Record<Tone, string> = {
  default: "",
  running: "",
  warning: "ring-2 ring-warning/50 ring-offset-2 ring-offset-background",
  accent: "ring-2 ring-accent/50 ring-offset-2 ring-offset-background",
};

function StageStep({ stage, state, tone }: { stage: PieceStage; state: RailStepState; tone: Tone }) {
  const isCurrent = state === "current";
  const variant = !isCurrent
    ? state === "done"
      ? "secondary"
      : "outline"
    : tone === "warning"
      ? "warning"
      : tone === "accent"
        ? "accent"
        : "default";

  let icon: React.ReactNode = null;
  if (isCurrent && tone === "running") {
    icon = <Loader2 className="h-3 w-3 animate-spin" aria-hidden />;
  } else if (isCurrent && tone === "warning") {
    icon = <AlertTriangle className="h-3 w-3" aria-hidden />;
  } else if (isBatchStage(stage)) {
    icon = <Cog className="h-3 w-3" aria-hidden />;
  }

  return (
    <Badge
      role="listitem"
      aria-current={isCurrent ? "step" : undefined}
      variant={variant}
      className={cn(state === "upcoming" && "text-muted-foreground/70", isCurrent && CURRENT_RING[tone])}
    >
      {icon}
      {stageLabel(stage)}
    </Badge>
  );
}

function ClusterLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
      {children}
    </p>
  );
}

function StageRow({
  stages,
  states,
  tone,
}: {
  stages: readonly RailStage[];
  states: Record<RailStage, RailStepState>;
  tone: Tone;
}) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {stages.map((s, i) => (
        <React.Fragment key={s}>
          <StageStep stage={s} state={states[s]} tone={tone} />
          {i < stages.length - 1 ? (
            <span className="text-muted-foreground/50" aria-hidden>
              &rarr;
            </span>
          ) : null}
        </React.Fragment>
      ))}
    </div>
  );
}

function PausedChip({ current }: { current: boolean }) {
  return (
    <Badge
      variant={current ? "warning" : "muted"}
      className={cn(current && CURRENT_RING.warning)}
      title="Off-rail: reachable from any interactive step (stop-for-the-day)"
    >
      <PauseCircle className="h-3 w-3" aria-hidden />
      paused
    </Badge>
  );
}

/**
 * The loop stages drawn as a bracket, not a straight line (`ALLOWED_TRANSITIONS` makes
 * `council ⇄ review ⇄ incorporating` a genuine cycle) — the round chip is always shown, even at
 * round 1 (muted) so the bracket reads as "hasn't looped yet" rather than absent; it escalates to
 * accent + an explicit loop count only once the piece has actually gone around more than once.
 */
function LoopBracket({
  stages,
  states,
  tone,
  round,
}: {
  stages: readonly RailStage[];
  states: Record<RailStage, RailStepState>;
  tone: Tone;
  round: number;
}) {
  const looping = round > 1;
  return (
    <div
      className={cn(
        "relative rounded-xl border border-dashed px-3 pb-2 pt-4",
        looping ? "border-accent/50 bg-accent/5" : "border-border",
      )}
    >
      <span
        className={cn(
          "absolute -top-2.5 left-3 inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold",
          looping ? "bg-accent text-accent-foreground" : "bg-muted text-muted-foreground",
        )}
      >
        <Repeat className="h-2.5 w-2.5" aria-hidden />
        round {round}
        {looping ? ` · loop ${round - 1}×` : ""}
      </span>
      <ClusterLabel>council &harr; review &harr; incorporating</ClusterLabel>
      <StageRow stages={stages} states={states} tone={tone} />
    </div>
  );
}

function PipelineRail({ piece, tone }: { piece: PieceDetail; tone: Tone }) {
  const states = railStepStates(piece.stage);
  const round = piece.review_round?.round_number ?? 1;

  return (
    <div role="list" aria-label="Piece lifecycle" className="flex flex-wrap items-stretch gap-3">
      <div>
        <ClusterLabel>Intake</ClusterLabel>
        <StageRow stages={stagesInCluster("intake")} states={states} tone={tone} />
      </div>
      <span className="self-center text-muted-foreground/50" aria-hidden>
        &rarr;
      </span>
      <LoopBracket stages={stagesInCluster("loop")} states={states} tone={tone} round={round} />
      <span className="self-center text-muted-foreground/50" aria-hidden>
        &rarr;
      </span>
      <div>
        <ClusterLabel>Ship</ClusterLabel>
        <StageRow stages={stagesInCluster("ship")} states={states} tone={tone} />
      </div>
      <span className="mx-1 self-center text-muted-foreground/30" aria-hidden>
        |
      </span>
      <div className="self-center">
        <PausedChip current={piece.stage === "paused"} />
      </div>
    </div>
  );
}

/** Equal visual weight to the primary button next to it (decision A) — informational only, never
 * a second control; the real action it names ("Capture lessons") is still a secondary button. */
function EqualWeightChip({ label }: { label: string }) {
  return (
    <span
      className={cn(
        buttonVariants({ size: "default" }),
        "pointer-events-none border-transparent bg-accent text-accent-foreground hover:bg-accent",
      )}
    >
      {label}
    </span>
  );
}

const CTA_ICON: Record<Tone, React.ComponentType<{ className?: string; "aria-hidden"?: boolean }>> = {
  default: CheckCircle2,
  running: CheckCircle2,
  warning: AlertTriangle,
  accent: CircleDot,
};

const CTA_DOT_CLASS: Record<Tone, string> = {
  default: "bg-primary/10 text-primary",
  running: "bg-primary/10 text-primary",
  warning: "bg-warning/20 text-warning",
  accent: "bg-accent/20 text-accent",
};

/**
 * The stage-contextual call to action, folded directly into the Pipeline block (no card boundary)
 * — this is the literal fix for "draw them to take action": the rail says where, this says what's
 * next, and (via `tone`) both agree on why. Fires the real orchestration trigger through the BFF,
 * same as the component this replaces (`NextActionCard`).
 */
function PipelineCta({
  piece,
  onUpdated,
  interviewerPersonas,
  tone,
}: {
  piece: PieceDetail;
  onUpdated: (next: PieceDetail) => void;
  interviewerPersonas: string[];
  tone: Tone;
}) {
  const [pending, setPending] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  // Explicit success readout (cmw-boss-facing-presentation, MEDIUM): the batch-chain POSTs block
  // until the job(s) finish and the piece is refetched — the status line names that outcome
  // instead of leaving the user to infer it from the rail alone. Cleared on the next fire.
  const [success, setSuccess] = React.useState<string | null>(null);
  const [openInterviewRoundExpanded, setOpenInterviewRoundExpanded] = React.useState(false);

  const action = nextAction(piece);
  const secondary = secondaryActions(piece);
  const openInterviewRoundAction = secondary.find((s) => s.kind === "open-interview-round");

  async function fire(trigger: string) {
    setPending(trigger);
    setError(null);
    setSuccess(null);
    try {
      const res = await fetch(`/api/pieces/${encodeURIComponent(piece.id)}/trigger`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ trigger }),
      });
      if (!res.ok) {
        const body = (await res.json().catch(() => null)) as { error?: string } | null;
        throw new Error(body?.error ?? `request failed (${res.status})`);
      }
      const refreshed = await fetch(`/api/pieces/${encodeURIComponent(piece.id)}`, {
        cache: "no-store",
      });
      if (refreshed.ok) {
        const next = (await refreshed.json()) as PieceDetail;
        onUpdated(next);
        setSuccess(`Done — the piece is now at ${stageLabel(next.stage)}.`);
      } else {
        setSuccess("Done — refresh the page to see the new state.");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "something went wrong");
    } finally {
      setPending(null);
    }
  }

  const Icon = CTA_ICON[tone];

  return (
    <div className="flex items-start gap-3 border-t pt-4">
      <span
        className={cn(
          "mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full",
          CTA_DOT_CLASS[tone],
        )}
        aria-hidden
      >
        <Icon className="h-3.5 w-3.5" />
      </span>
      <div className="flex min-w-0 flex-1 flex-col gap-3">
        <p className="text-sm text-muted-foreground">
          This piece is in <b className="text-foreground">{stageLabel(piece.stage)}</b>. {action.description}
        </p>

        <div className="flex flex-wrap items-center gap-2">
          {action.kind === "trigger" ? (
            <>
              <Button onClick={() => fire(action.trigger)} disabled={pending !== null}>
                {pending === action.trigger ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : null}
                {action.label}
              </Button>
              {action.chip ? <EqualWeightChip label={action.chip.label} /> : null}
            </>
          ) : action.kind === "link" ? (
            <Button asChild>
              <Link href={action.href}>{action.label}</Link>
            </Button>
          ) : action.kind === "propose-lessons" ? (
            <ProposeLessonsForm pieceId={piece.id} onUpdated={onUpdated} />
          ) : (
            <div className="rounded-md border bg-muted/40 px-3 py-2 text-center text-sm text-muted-foreground">
              {action.label}
            </div>
          )}

          {secondary.map((s) => {
            if (s.kind === "link") {
              return (
                <Button key={s.href} asChild variant="outline" size="sm" title={s.description}>
                  <Link href={s.href}>{s.label}</Link>
                </Button>
              );
            }
            if (s.kind === "open-interview-round") {
              return (
                <Button
                  key="open-interview-round"
                  variant="outline"
                  size="sm"
                  title={s.description}
                  aria-expanded={openInterviewRoundExpanded}
                  onClick={() => setOpenInterviewRoundExpanded((v) => !v)}
                >
                  {s.label}
                </Button>
              );
            }
            return (
              <Button
                key={s.trigger}
                variant="outline"
                size="sm"
                onClick={() => fire(s.trigger)}
                disabled={pending !== null}
                title={s.description}
              >
                {pending === s.trigger ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : null}
                {s.label}
              </Button>
            );
          })}
        </div>

        {openInterviewRoundExpanded && openInterviewRoundAction ? (
          <OpenInterviewRoundForm
            pieceId={piece.id}
            personas={interviewerPersonas}
            roundNumber={openInterviewRoundAction.roundNumber}
            onUpdated={onUpdated}
          />
        ) : null}

        {error ? <Alert>{error}</Alert> : null}
        {success ? <Alert variant="success">{success}</Alert> : null}

        {/* Folded in from the old top-of-page failure banner (decision B) — the same detail, just
            living in the one block that now owns "what's going on with this piece." */}
        {piece.failures.length > 0 ? (
          <Alert variant="warning">
            <div>
              <p className="font-medium text-foreground">Warns, doesn&rsquo;t block</p>
              <ul className="mt-1 list-disc pl-5">
                {piece.failures.map((f, i) => (
                  <li key={i}>
                    Error code <span className="font-mono text-xs">{f.code}</span> ({f.type} job): {f.message} &mdash;{" "}
                    {f.retryable ? "transient, retrying may clear it." : "retry, or edit inputs first."}
                  </li>
                ))}
              </ul>
            </div>
          </Alert>
        ) : null}

        <p className="text-xs text-muted-foreground">
          <b className="text-foreground">Flat auth:</b> anyone signed in can act on this piece, not just
          the owner. Ownership only sorts it into your dashboard and defaults the “needs my action”
          filter.
        </p>
      </div>
    </div>
  );
}

export function Pipeline({
  piece,
  onUpdated,
  interviewerPersonas = [],
}: {
  piece: PieceDetail;
  onUpdated: (next: PieceDetail) => void;
  /** The interviewer persona roster — only consumed by the review-stage "Start another round of
   * interviews" action. Defaults to empty so every existing caller/test stays valid without
   * threading it through. */
  interviewerPersonas?: string[];
}) {
  const tone = pipelineTone(piece);
  const [refExpanded, setRefExpanded] = React.useState(false);
  // Decision D: dim the whole block to read as "parked" — purely visual, every control below
  // stays fully actionable (archiving changes nothing else about the piece).
  const archived = Boolean(piece.archived_at);

  return (
    <Card className={cn(archived && "opacity-60")}>
      <CardHeader>
        <CardTitle className="text-lg">Pipeline</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <PipelineRail piece={piece} tone={tone} />
        <PipelineCta
          piece={piece}
          onUpdated={onUpdated}
          interviewerPersonas={interviewerPersonas}
          tone={tone}
        />
        <div className="border-t pt-3">
          <div className="flex items-center gap-1.5">
            <ExpandToggle
              expanded={refExpanded}
              onToggle={() => setRefExpanded((v) => !v)}
              label="the full stage → action reference table"
            />
            <span className="text-sm text-muted-foreground">
              {refExpanded ? "Hide" : "Show"} full stage &rarr; action reference
            </span>
          </div>
          {refExpanded ? (
            <div className="mt-2">
              <StageActionReference current={piece.stage} />
            </div>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}
