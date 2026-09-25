"use client";

import * as React from "react";

import { Badge } from "@/components/ui/badge";
import { ExpandToggle } from "@/components/ui/expand-toggle";
import type { EvidenceCitation, EvidenceSource } from "@/lib/pieces/types";
import { cn } from "@/lib/utils";

/**
 * The expandable sources drawer (v1 launch wave, "evidence-ui-scope"): the FULL retrieval/source
 * list behind a draft's claim-level citation chips. Claim chips stay inline in the draft body by
 * default (they're the draft's own `<sup class="fn">` markers, rendered as small chips by
 * globals.css); everything they stand on — the draft's footnote sources plus the research
 * citations in `sources.md` — lives in this drawer, collapsed until asked for.
 *
 * Clicking a chip in the draft opens the drawer and scrolls to + briefly highlights the exact
 * source entry (DraftView wires that via `openSignal`); clicking a chip badge inside the drawer
 * jumps back to the claim in the draft body when its in-draft anchor is present.
 */
export function SourcesDrawer({
  sources,
  citations,
  openSignal,
}: {
  sources: EvidenceSource[];
  citations: EvidenceCitation[];
  /** Bumped by DraftView every time a draft-body chip is clicked; carries the source id to
   * reveal. `{id: null}` resets without highlighting (plain "show sources" clicks). */
  openSignal: { seq: number; sourceId: string | null };
}) {
  const [expanded, setExpanded] = React.useState(false);
  const [highlightId, setHighlightId] = React.useState<string | null>(null);
  const entryRefs = React.useRef(new Map<string, HTMLElement>());
  const lastSeq = React.useRef(0);

  // A chip click in the draft body: open, then scroll to + flash the matching entry. Done in an
  // effect (not the click handler) because the entry DOM only exists once `expanded` rendered.
  React.useEffect(() => {
    if (openSignal.seq === lastSeq.current) return;
    lastSeq.current = openSignal.seq;
    setExpanded(true);
    setHighlightId(openSignal.sourceId);
  }, [openSignal]);

  React.useEffect(() => {
    if (!expanded || !highlightId) return;
    const node = entryRefs.current.get(highlightId);
    node?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    const timer = setTimeout(() => setHighlightId(null), 1600);
    return () => clearTimeout(timer);
  }, [expanded, highlightId]);

  if (sources.length === 0) return null;

  const footnotes = sources.filter((s) => s.kind === "footnote");
  const research = sources.filter((s) => s.kind === "sources-md");
  const sections = new Map<string, EvidenceSource[]>();
  for (const entry of research) {
    const key = entry.section ?? "";
    sections.set(key, [...(sections.get(key) ?? []), entry]);
  }

  return (
    <div className="rounded-lg border">
      <div className="flex items-center gap-2 px-3 py-2">
        <ExpandToggle
          expanded={expanded}
          onToggle={() => setExpanded((v) => !v)}
          label="Sources & retrieval"
        />
        <button
          type="button"
          className="text-sm font-medium hover:opacity-80"
          onClick={() => setExpanded((v) => !v)}
        >
          Sources &amp; retrieval
        </button>
        <span className="text-xs text-muted-foreground">
          {footnotes.length > 0
            ? `${citations.length} claim chip${citations.length === 1 ? "" : "s"} · `
            : ""}
          {sources.length} source{sources.length === 1 ? "" : "s"}
        </span>
      </div>
      {expanded ? (
        <div
          data-testid="sources-drawer-body"
          className="flex flex-col gap-3 border-t px-3 py-3 text-sm"
        >
          {footnotes.length > 0 ? (
            <DrawerGroup
              title="Cited in the draft"
              entries={footnotes}
              highlightId={highlightId}
              entryRefs={entryRefs.current}
              citations={citations}
            />
          ) : null}
          {[...sections.entries()].map(([section, entries]) => (
            <DrawerGroup
              key={section || "(untitled section)"}
              title={section || "sources.md"}
              entries={entries}
              highlightId={highlightId}
              entryRefs={entryRefs.current}
              citations={citations}
            />
          ))}
          <p className="text-xs text-muted-foreground">
            Parsed read-time from the piece&rsquo;s own Git content — the draft&rsquo;s footnote
            sources and <span className="font-mono">sources.md</span>&rsquo;s research citations.
          </p>
        </div>
      ) : null}
    </div>
  );
}

function DrawerGroup({
  title,
  entries,
  highlightId,
  entryRefs,
  citations,
}: {
  title: string;
  entries: EvidenceSource[];
  highlightId: string | null;
  entryRefs: Map<string, HTMLElement>;
  citations: EvidenceCitation[];
}) {
  return (
    <div>
      <p className="mb-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {title}
      </p>
      <ul className="flex flex-col gap-1.5">
        {entries.map((entry) => (
          <SourceEntry
            key={entry.id}
            entry={entry}
            highlighted={highlightId === entry.id}
            registerRef={(node) => {
              if (node) entryRefs.set(entry.id, node);
              else entryRefs.delete(entry.id);
            }}
            chipAnchor={chipBackAnchor(entry, citations)}
          />
        ))}
      </ul>
    </div>
  );
}

/** The chip's in-draft anchor (e.g. `#r2`), when this source is cited — powers the
 * drawer → claim jump. */
function chipBackAnchor(
  entry: EvidenceSource,
  citations: EvidenceCitation[],
): { href: string; chip: string } | null {
  const citation = citations.find((c) => c.source_id === entry.id && c.anchor_id);
  if (!citation || !entry.chip) return null;
  return { href: `#${citation.anchor_id}`, chip: citation.chip };
}

function SourceEntry({
  entry,
  highlighted,
  registerRef,
  chipAnchor,
}: {
  entry: EvidenceSource;
  highlighted: boolean;
  registerRef: (node: HTMLElement | null) => void;
  chipAnchor: { href: string; chip: string } | null;
}) {
  return (
    <li
      ref={registerRef}
      data-testid={`source-entry-${entry.id}`}
      className={cn(
        "rounded-md border px-2.5 py-1.5 transition-colors duration-500",
        highlighted ? "border-warning bg-warning/10" : "border-transparent bg-muted/30",
      )}
    >
      <span className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
        {entry.chip ? (
          chipAnchor ? (
            <a
              href={chipAnchor.href}
              title="Jump to the claim in the draft"
              className="inline-flex min-w-[1.4em] items-center justify-center rounded-full border border-current px-1.5 text-xs font-semibold no-underline"
            >
              {entry.chip}
            </a>
          ) : (
            <Badge variant="outline">{entry.chip}</Badge>
          )
        ) : null}
        <span className="min-w-0 flex-1">{entry.label}</span>
      </span>
      {entry.urls.length > 0 ? (
        <span className="mt-0.5 flex flex-col gap-0.5">
          {entry.urls.map((url) => (
            <a
              key={url}
              href={url}
              target="_blank"
              rel="noreferrer"
              className="break-all text-xs underline"
            >
              {url}
            </a>
          ))}
        </span>
      ) : null}
    </li>
  );
}
