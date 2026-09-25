"use client";

import * as React from "react";
import { Josefin_Sans, JetBrains_Mono } from "next/font/google";

import { SourcesDrawer } from "@/components/piece-detail/sources-drawer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { CollapsibleSection } from "@/components/ui/collapsible-section";
import { Modal } from "@/components/ui/modal";
import { draftExcerpt, parseDraftHtml, plainTextLength } from "@/lib/pieces/draft-html";
import type { EvidenceCitation, EvidenceSource } from "@/lib/pieces/types";
import { cn } from "@/lib/utils";

// The content preview below must render the reader-facing brand identity (visual-identity.md)
// regardless of how the app's own chrome is re-skinned (cmw-app-chrome-reskin-fix) — loaded here
// independently of app/layout.tsx's own chrome fonts, so swapping the chrome's --font-serif/
// --font-sans (or the fonts layout.tsx imports for them) can never affect this preview. Paired
// with the frozen, non-token `.piece-content-preview` CSS block in app/globals.css.
const previewSerif = Josefin_Sans({
  subsets: ["latin"],
  variable: "--preview-font-serif",
  display: "swap",
  weight: ["700"]
});
const previewSans = Josefin_Sans({
  subsets: ["latin"],
  variable: "--preview-font-sans",
  display: "swap",
  weight: ["300", "400"]
});

const PREVIEW_CLASS = "piece-content-preview max-w-none rounded-lg border p-6 text-sm leading-relaxed";

// Roughly "longer than a substantial LinkedIn post" — under this, a tweet/LinkedIn-post-sized
// piece renders in full with no clamp/modal at all (Hendo: small content must not look broken or
// empty); over it, a long/complex piece clamps to a fixed height with a modal to read the rest
// (the actual "giant page" problem). The section itself is always expanded when content exists.
const LONG_CONTENT_CHARS = 2000;
// A fixed pixel clamp (not a Tailwind scale step) because it has to match the fade overlay's own
// height/position exactly — a `max-h-*` utility class would work for the clamp alone, but the
// fade needs the same literal value to blend at the same edge.
const CLAMP_HEIGHT_PX = 420;

/**
 * The left body of the piece-detail screen: the semantic `draft.html` master plus its trailing
 * `<section class="editorial">` GAP/clearance block, shown as a visible, labeled sub-section
 * rather than hidden — this is exactly the block external-share (D11) and finalize (D13) strip via
 * one shared routine, so showing it here tells the owner what's still open before either of those.
 *
 * `draft_html` is trusted, git-committed content the internal pipeline writes (never third-party
 * user input), rendered inline so the actual authored HTML (headings, figures, inlined SVG) reads
 * as prose rather than an opaque blob.
 *
 * Owns its own `CollapsibleSection` (cmw-piece-detail-collapsible) rather than being wrapped by
 * one in `piece-detail-view.tsx`. Content that exists is ALWAYS expanded on landing
 * (cmw-piece-draft-visibility) — a collapsed card titled only with a git SHA made users wonder
 * whether a draft even existed (live: the Amazon Quick + Hendo brain-synced brief, and every
 * other in-progress piece). Length still decides clamp-vs-full inside the body (short pieces
 * render in full; long ones clamp with a modal), never whether the body is shown at all. The
 * trailing editorial block is `pinned`: visible regardless of the body's collapse state, same
 * "must not miss" treatment as the piece-wide failures banner, since it's exactly the open-GAP/
 * clearance list a piece owner must see before finalizing.
 *
 * The rendered face itself (background/ink/heading+body typography/link color) is deliberately
 * NOT chrome-token-driven — see `.piece-content-preview` in app/globals.css. Only the surrounding
 * frame (border/radius/padding) still follows the app's own tokens, since that's chrome presenting
 * the content, never something a reader of the real branded output would ever see. The trailing
 * editorial block below is the opposite case on purpose: it never reaches a real reader (D11/D13
 * strip it), so it stays fully chrome-styled (warning tokens), not frozen.
 */
export function DraftView({
  draftHtml,
  revision,
  sources = [],
  citations = [],
  brainSynced = false,
}: {
  draftHtml: string | null;
  revision: string | null;
  /** The piece's evidence trail (agents `app.evidence`, carried on PieceDetail): footnote +
   * sources.md entries for the expandable drawer, and the claim chips that reference them.
   * Absent/empty means the piece carries no evidence annotations — no drawer, chips as-is. */
  sources?: EvidenceSource[];
  citations?: EvidenceCitation[];
  /** True when this record was registered from a brain-authored drafts/ folder — the badge
   * then reads "brain draft" so a synced seller brief isn't labelled as a pipeline revision. */
  brainSynced?: boolean;
}) {
  const parsed = draftHtml ? parseDraftHtml(draftHtml) : null;
  const isLong = parsed ? plainTextLength(parsed.bodyHtml) > LONG_CONTENT_CHARS : false;

  // Chip-click wiring (claim-level citations, v1 "evidence-ui-scope"): a chip in the draft body
  // opens the sources drawer scrolled to its entry. `seq` makes repeat clicks on the same chip
  // re-fire the reveal; `sourceId: null` never highlights.
  const [openSignal, setOpenSignal] = React.useState<{ seq: number; sourceId: string | null }>({
    seq: 0,
    sourceId: null,
  });
  const knownSourceIds = React.useMemo(() => new Set(sources.map((s) => s.id)), [sources]);
  const handleCitationClick = React.useCallback(
    (sourceId: string) => {
      setOpenSignal((prev) => ({ seq: prev.seq + 1, sourceId }));
    },
    [],
  );

  if (!draftHtml || !parsed) {
    return (
      <CollapsibleSection title="Current content" empty>
        <div className="rounded-lg border border-dashed bg-muted/30 p-6 text-center text-sm text-muted-foreground">
          No content yet — the draft appears once it has been written.
        </div>
      </CollapsibleSection>
    );
  }

  const { bodyHtml, editorialHtml } = parsed;
  const previewClassName = cn(PREVIEW_CLASS, previewSerif.variable, previewSans.variable);
  const excerpt = draftExcerpt(bodyHtml);

  return (
    <CollapsibleSection
      title="Current content"
      // Always expanded on landing when content exists (cmw-piece-draft-visibility). Length only
      // decides clamp-vs-full inside DraftBody — collapsing hid the piece itself behind a SHA.
      defaultExpanded
      pinned={
        editorialHtml ? (
          <EditorialBlock html={editorialHtml} />
        ) : undefined
      }
      summary={
        <span>
          {excerpt ? <span className="italic">{excerpt}</span> : null}
          {revision ? <span className="ml-1.5 font-mono">{revision}</span> : null}
          {isLong ? <Badge variant="muted" className="ml-1.5">long</Badge> : null}
        </span>
      }
    >
      <div className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="text-sm font-medium">
            Current content
            {revision ? <span className="ml-1.5 font-mono text-muted-foreground">{revision}</span> : null}
          </span>
          <Badge variant="muted">{brainSynced ? "brain draft" : "master draft"}</Badge>
        </div>

        <DraftBody
          html={bodyHtml}
          isLong={isLong}
          previewClassName={previewClassName}
          knownSourceIds={knownSourceIds}
          onCitationClick={handleCitationClick}
        />

        {/* Claim chips stay inline in the draft above (their default face); the full
            retrieval/source list they stand on lives in this expandable drawer. */}
        <SourcesDrawer sources={sources} citations={citations} openSignal={openSignal} />
      </div>
    </CollapsibleSection>
  );
}

/**
 * The actual `draft.html` body — full inline for a short/tweet-sized piece, clamped to a fixed
 * height with a fade + "Read full draft" modal for anything longer (cmw-piece-detail-collapsible:
 * "modal pop-ups for long-form content"). `isLong` is computed once by the caller from the same
 * plain-text length; it only decides clamp-vs-full here, never whether the section is shown.
 *
 * Citation-chip clicks (`<sup class="fn"><a href="#srcN">…`) are intercepted here via event
 * delegation and routed to the sources drawer instead of hash-navigating — but ONLY when the
 * href references a source the backend actually parsed (a hand-authored `#something-else`
 * anchor keeps its native in-document behavior).
 */
function DraftBody({
  html,
  isLong,
  previewClassName,
  knownSourceIds,
  onCitationClick,
}: {
  html: string;
  isLong: boolean;
  previewClassName: string;
  knownSourceIds: ReadonlySet<string>;
  onCitationClick: (sourceId: string) => void;
}) {
  const [modalOpen, setModalOpen] = React.useState(false);

  const handleClick = (event: React.MouseEvent<HTMLDivElement>) => {
    const target = event.target instanceof Element ? event.target.closest("a") : null;
    if (!target) return;
    const href = target.getAttribute("href") ?? "";
    if (!href.startsWith("#")) return;
    const sourceId = href.slice(1);
    if (!knownSourceIds.has(sourceId)) return;
    event.preventDefault();
    onCitationClick(sourceId);
  };

  if (!isLong) {
    // draft.html is trusted, internally-authored content (Git brain, D1/D2/D4) — see module doc.
    return (
      <div
        className={previewClassName}
        onClick={handleClick}
        dangerouslySetInnerHTML={{ __html: html }}
      />
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="relative">
        <div
          className={previewClassName}
          style={{ maxHeight: CLAMP_HEIGHT_PX, overflow: "hidden" }}
          onClick={handleClick}
          dangerouslySetInnerHTML={{ __html: html }}
        />
        <div
          aria-hidden
          className="pointer-events-none absolute inset-x-0 bottom-0 rounded-b-lg"
          style={{ height: 96, backgroundImage: "linear-gradient(to top, #fdf6ea, transparent)" }}
        />
      </div>
      <Button variant="outline" size="sm" className="self-start" onClick={() => setModalOpen(true)}>
        Read full draft
      </Button>
      <Modal
        open={modalOpen}
        onOpenChange={setModalOpen}
        title="Current content — full draft"
        contentClassName="max-w-4xl"
      >
        <div
          className={previewClassName}
          onClick={handleClick}
          dangerouslySetInnerHTML={{ __html: html }}
        />
      </Modal>
    </div>
  );
}

function EditorialBlock({ html }: { html: string }) {
  return (
    <div className="rounded-lg border border-dashed border-warning/40 bg-warning/5 p-4">
      <Badge variant="warning">Not for publication</Badge>
      <div
        className="mt-2 max-w-none text-sm leading-relaxed [&_h3]:mb-1 [&_h3]:font-medium [&_p]:my-1.5"
        dangerouslySetInnerHTML={{ __html: html }}
      />
      <p className="mt-2 text-xs text-muted-foreground">
        External shares and finalize both strip this block. Always shown regardless of the
        revision above being collapsed — it&rsquo;s the open-gap/clearance list a piece owner must
        not miss.
      </p>
    </div>
  );
}
