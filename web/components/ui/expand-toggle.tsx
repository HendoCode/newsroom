import * as React from "react";
import { ChevronDown, ChevronRight } from "lucide-react";

import { cn } from "@/lib/utils";

/**
 * The ONE collapsed-row / expand-on-click affordance for this app's list surfaces (Hendo,
 * 2026-08-10 — the dashboard queue and the source registry table are "the sole authoritative
 * 'where do I find X again' surface," so their rows must stay a line or two at scale, with detail
 * revealed on demand rather than always rendered). Both `PieceCard` and `SourcesTable` use this
 * same button so a collapsed row always looks and behaves identically regardless of which list
 * it's in — a future third list should reuse this rather than inventing its own toggle.
 */
export function ExpandToggle({
  expanded,
  onToggle,
  label,
  className,
}: {
  expanded: boolean;
  onToggle: () => void;
  /** Accessible name, e.g. "A piece" or "Call & webinar transcripts" — announced as "Show more
   * details about {label}" / "Show less". */
  label: string;
  className?: string;
}) {
  const Icon = expanded ? ChevronDown : ChevronRight;
  return (
    <button
      type="button"
      aria-expanded={expanded}
      onClick={onToggle}
      title={expanded ? `Show less — ${label}` : `Show more details — ${label}`}
      className={cn(
        "flex shrink-0 items-center justify-center rounded-md p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground",
        className,
      )}
    >
      <Icon className="h-4 w-4" aria-hidden />
      <span className="sr-only">
        {expanded ? `Show less — ${label}` : `Show more details — ${label}`}
      </span>
    </button>
  );
}
