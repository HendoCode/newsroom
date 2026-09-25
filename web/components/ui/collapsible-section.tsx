"use client";

import * as React from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ExpandToggle } from "@/components/ui/expand-toggle";
import { cn } from "@/lib/utils";

/**
 * A whole-Card counterpart to `ExpandToggle` (same file's sibling): the identical collapsed-by-
 * default, expand-on-click idiom PR #89 established for list rows (dashboard queue, source
 * registry), generalized to a full page SECTION. Piece detail (cmw-piece-detail-collapsible) is
 * the first caller — a page with many Cards, each serving a different task, needs most of them
 * collapsed on landing so the ones that actually answer "what stage is this at, what do I do
 * next" aren't buried under reference/history detail. Reuse this for any future page section
 * rather than inventing a second collapsed-section idiom.
 *
 * Carries forward both PR #89 decisions: `summary` keeps the headline fact scannable even
 * collapsed (mirrors a collapsed row's compact meta strip), `pinned` renders content the user
 * must not miss regardless of collapse state (mirrors "errors stay visible"), and `empty` skips
 * the toggle entirely when there is genuinely nothing to expand.
 */
export function CollapsibleSection({
  title,
  summary,
  defaultExpanded = false,
  empty = false,
  pinned,
  children,
  className,
}: {
  title: string;
  /** Always-visible next to the title, collapsed or not — e.g. "Aggregate 8.0 · round 2". */
  summary?: React.ReactNode;
  defaultExpanded?: boolean;
  /** True when there's nothing to expand at all (PR #89's rule) — `children` renders directly
   * with no toggle, as the section's permanent content. */
  empty?: boolean;
  /** Rendered regardless of collapse state — for content the user must not miss even
   * collapsed (e.g. a "Resume interview" link). */
  pinned?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  const [expanded, setExpanded] = React.useState(defaultExpanded);
  const showBody = empty || expanded;

  return (
    <Card className={className}>
      <CardHeader className="flex-row flex-wrap items-center justify-between gap-x-3 gap-y-1 space-y-0">
        <div className="flex min-w-0 items-center gap-2">
          {!empty ? (
            <ExpandToggle expanded={expanded} onToggle={() => setExpanded((v) => !v)} label={title} />
          ) : null}
          <CardTitle className="text-lg">{title}</CardTitle>
        </div>
        {summary ? (
          <div className="min-w-0 text-sm text-muted-foreground">{summary}</div>
        ) : null}
      </CardHeader>
      {pinned ? <CardContent className="pt-0">{pinned}</CardContent> : null}
      {showBody ? (
        <CardContent className={cn(pinned && "pt-0")}>{children}</CardContent>
      ) : null}
    </Card>
  );
}
