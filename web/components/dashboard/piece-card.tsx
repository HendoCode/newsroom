import * as React from "react";
import Link from "next/link";
import { AlertTriangle, Archive, Loader2, Edit } from "lucide-react";

import { PipelineMiniRail } from "@/components/dashboard/pipeline-mini-rail";
import { SpikeStatusBadge, StageBadge } from "@/components/dashboard/stage-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ExpandToggle } from "@/components/ui/expand-toggle";
import { primaryAction, relationshipLabel } from "@/lib/dashboard/actions";
import { needsMyAction } from "@/lib/dashboard/needs-my-action";
import type { QueueItem } from "@/lib/dashboard/types";
import { relativeTime } from "@/lib/format/relative-time";
import { humanTouchStaleness } from "@/lib/format/staleness";
import { cn } from "@/lib/utils";

/**
 * The queue's piece/spike card (cmw-ui-wireframes screen 1). This is the SHARED card component the
 * later piece-detail / spikes screens will reuse — kept free of tab/filter concerns so it drops
 * into any list. Collapsed by default to a line or two — title/badges + a compact meta strip —
 * with the "why here" reasoning and the full failed-job explanation behind an `ExpandToggle`
 * (Hendo, 2026-08-10: this queue is "the only list of these kinds of things anywhere," so it has
 * to stay scannable once real usage piles in many rows, not just look fine with a handful).
 * Attribution only — no field here gates anything (§1.17). Fully token-driven.
 */
export function PieceCard({
  item,
  email,
  showWhy = false,
  onArchive,
  onRename,
  now,
}: {
  item: QueueItem;
  email: string | null | undefined;
  /** Show the "Why here" attribution line + relationship chip (the "Needs my action" tab). */
  showWhy?: boolean;
  /** Archive this piece from the list, no need to open it first (triage at scale). Only rendered
   * for `kind === "piece"` — spikes have no archive concept. Omitted entirely on surfaces that
   * don't offer archiving from the list. */
  onArchive?: (item: QueueItem) => void | Promise<void>;
  /** Rename this piece from the list — only for `kind === "piece"`. */
  onRename?: (item: QueueItem, newTitle: string) => void | Promise<void>;
  /** Clock for the staleness-triage timestamps below — a caller rendering a whole list should
   * capture this once (`React.useMemo(() => new Date(), [])`, matching `Dashboard`'s own D15
   * date-axis clock) rather than let every card read a slightly different "now". Defaults to a
   * fresh `Date` for a standalone card. */
  now?: Date;
}) {
  const needs = needsMyAction(email, item);
  const action = primaryAction(item, needs, email);
  const who = (v: string | null) => (v && v === email ? "you" : v);
  const [archiving, setArchiving] = React.useState(false);
  const [renaming, setRenaming] = React.useState(false);
  const [expanded, setExpanded] = React.useState(false);
  // Only used as a fallback when no caller-supplied clock is given (a standalone card, e.g. a
  // test) — mounted once, not re-read on every render.
  const mountedAt = React.useMemo(() => new Date(), []);
  const clock = now ?? mountedAt;

  // Only the "why here" reasoning and the failed-job explanation are hidden behind the toggle —
  // everything else (title, badges, the compact meta strip, actions) is already a line or two and
  // stays visible so the card is identifiable at a glance without a click.
  const hasExpandableContent = Boolean((showWhy && needs) || item.failed_job);

  async function handleArchive() {
    setArchiving(true);
    try {
      await onArchive?.(item);
    } finally {
      setArchiving(false);
    }
  }

  async function handleRename() {
    if (!onRename) return;
    const newTitle = window.prompt("Rename piece", item.title || "");
    if (newTitle === null) return; // cancelled
    if (newTitle === item.title) return; // unchanged
    setRenaming(true);
    try {
      await onRename(item, newTitle);
    } finally {
      setRenaming(false);
    }
  }

  return (
    <Card className="flex flex-col gap-2 p-3">
      <div className="flex flex-wrap items-start gap-3 sm:items-center sm:justify-between">
        <div className="flex min-w-0 flex-1 items-start gap-2">
          {hasExpandableContent ? (
            <ExpandToggle
              expanded={expanded}
              onToggle={() => setExpanded((v) => !v)}
              label={item.title}
              className="mt-0.5"
            />
          ) : null}
          <div className="flex min-w-0 flex-col gap-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className="truncate font-serif text-base font-semibold">{item.title}</span>
              {item.kind === "piece" && onRename && (
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={handleRename}
                  disabled={renaming}
                  title="Rename piece"
                  className="h-6 w-6"
                >
                  {renaming ? (
                    <Loader2 className="h-3 w-3 animate-spin" aria-hidden />
                  ) : (
                    <Edit className="h-3 w-3" aria-hidden />
                  )}
                </Button>
              )}
              {item.kind === "piece" && item.stage ? (
                <>
                  <StageBadge stage={item.stage} round={item.review_round} />
                  <PipelineMiniRail stage={item.stage} round={item.review_round} />
                </>
              ) : null}
              {item.kind === "piece" && item.brain_synced ? (
                <Badge
                  variant="outline"
                  title="Registered from a brain-authored drafts/ folder; its content reads straight from the brain, it never went through the interview → draft → council pipeline"
                >
                  Brain draft
                </Badge>
              ) : null}
              {item.kind === "spike" && item.spike_status ? (
                <SpikeStatusBadge status={item.spike_status} />
              ) : null}
              {item.failed_job ? (
                <Badge variant="warning">
                  <AlertTriangle className="h-3 w-3" aria-hidden />
                  {item.failed_job.type} job failed
                </Badge>
              ) : null}
            </div>

            <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-sm text-muted-foreground">
              {item.voice ? (
                <span>
                  voice <b className="text-foreground">{item.voice}</b>
                </span>
              ) : null}
              {item.owner ? (
                <span>
                  owner <b className="text-foreground">{who(item.owner)}</b>
                </span>
              ) : null}
              {item.assigned_experts.length > 0 ? (
                <span>
                  assigned{" "}
                  <b className="text-foreground">
                    {item.assigned_experts.map((e) => who(e)).join(", ")}
                  </b>
                </span>
              ) : null}
              {item.creator && item.kind === "spike" ? (
                <span>
                  by <b className="text-foreground">{who(item.creator)}</b>
                </span>
              ) : null}
              {item.council_aggregate != null ? (
                <span>
                  council <b className="text-foreground">{item.council_aggregate.toFixed(1)}</b>
                </span>
              ) : null}
              {item.open_gaps > 0 ? (
                <span>
                  open GAPs <b className="text-foreground">{item.open_gaps}</b>
                </span>
              ) : null}
              {/* Staleness triage (cmw-staleness-timestamps): `updated` is "any write, including a
                  machine-only batch job"; `human` is "a person actually acted on this" — never
                  conflate the two, or the field lies about a job completion being a human touch.
                  `human` only exists for pieces (spikes carry no human-touch tracking). */}
              {item.updated_at ? (
                <span title="Last write of any kind, including a background job">
                  updated <b className="text-foreground">{relativeTime(item.updated_at, clock)}</b>
                </span>
              ) : null}
              {item.kind === "piece" ? (
                <span title="Last time a person acted on this piece (a stage trigger, or an interview answer/edit)">
                  human{" "}
                  <b
                    className={cn(
                      humanTouchStaleness(item.last_human_touch_at, clock) === "fresh"
                        ? "text-foreground"
                        : "text-warning",
                    )}
                  >
                    {item.last_human_touch_at ? relativeTime(item.last_human_touch_at, clock) : "never"}
                  </b>
                </span>
              ) : null}
            </div>
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-2">
          {item.kind === "piece" && onArchive ? (
            <Button
              variant="outline"
              size="sm"
              onClick={handleArchive}
              disabled={archiving}
              title="Hide from the dashboard — reversible, changes nothing else"
            >
              {archiving ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
              ) : (
                <Archive className="h-4 w-4" aria-hidden />
              )}
              Archive
            </Button>
          ) : null}
          <Button asChild size="sm">
            <Link href={action.href}>{action.label}</Link>
          </Button>
        </div>
      </div>

      {expanded ? (
        <div className="flex flex-col gap-2 pl-8">
          {showWhy && needs ? (
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="muted">{relationshipLabel(needs.relationship)}</Badge>
              <p className="text-sm text-muted-foreground">
                <span className="font-medium text-foreground">Why here:</span> {needs.why}
              </p>
            </div>
          ) : null}

          {item.failed_job ? (
            // Warns-not-blocks (§5): the one sanctioned hard block is the per-run cost ceiling
            // (D14); even that only FLAGS the piece — it stays at its last stable stage, fully
            // recoverable.
            <div className="rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-sm">
              <span className="font-medium text-foreground">Warns, doesn’t wedge</span> —{" "}
              <span className="font-mono text-xs">{item.failed_job.code}</span>: {item.failed_job.message}.{" "}
              {item.failed_job.retryable ? "Transient — retrying may clear it." : "Retry, or edit inputs first."}
            </div>
          ) : null}
        </div>
      ) : null}
    </Card>
  );
}
