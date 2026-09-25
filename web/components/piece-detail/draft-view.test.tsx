import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { DraftView } from "@/components/piece-detail/draft-view";
import type { EvidenceCitation, EvidenceSource } from "@/lib/pieces/types";

// jsdom has no real layout engine, so scrollIntoView isn't implemented at all (same stub as
// source-registry.test.tsx) — the sources drawer's reveal path calls it.
Element.prototype.scrollIntoView = vi.fn();

const DRAFT_HTML = `<html><body>
<h1>Why Data-Centre Diversification Matters</h1>
<p>Three customer conversations converged on the same theme.</p>
<section class="editorial">
<h3>Open items</h3>
<p>[GAP: need a named customer quote]</p>
</section>
</body></html>`;

// A tweet-sized draft — well under DraftView's LONG_CONTENT_CHARS threshold — for the "small
// content must not look broken/empty, and must not need a click to see" case.
const TWEET_HTML = `<html><body>
<p>Three customer conversations converged on the same theme this week.</p>
</body></html>`;

// Comfortably over the threshold — repeats a paragraph until the plain-text length is long-form.
const LONG_HTML = `<html><body>
<h1>A Much Longer, Complex Piece</h1>
${Array.from(
  { length: 40 },
  (_, i) => `<p>Paragraph ${i}: this sentence exists only to push the plain-text length of this fixture well past DraftView's long-content threshold so the clamp-and-modal path is actually exercised by this test.</p>`,
).join("\n")}
</body></html>`;

describe("DraftView", () => {
  it("shows the empty state when there is no content yet", () => {
    render(<DraftView draftHtml={null} revision={null} />);
    expect(screen.getByText(/no content yet/i)).toBeInTheDocument();
  });

  it("renders the body content", () => {
    render(<DraftView draftHtml={DRAFT_HTML} revision="abc123" />);
    const heading = screen.getByRole("heading", { name: /why data-centre diversification matters/i });
    expect(heading).toBeInTheDocument();
    expect(heading.closest(".piece-content-preview")).toHaveTextContent(
      /three customer conversations converged/i,
    );
  });

  it("renders the content face with the frozen preview class, never the app chrome's own tokens", () => {
    render(<DraftView draftHtml={DRAFT_HTML} revision="abc123" />);
    const heading = screen.getByRole("heading", { name: /why data-centre diversification matters/i });
    const preview = heading.closest("div");
    expect(preview).not.toBeNull();
    // The frozen, non-token face class — this is what app/globals.css's `.piece-content-preview`
    // block targets; re-skinning :root/.dark cannot reach in here.
    expect(preview).toHaveClass("piece-content-preview");
    // The chrome-token utility classes this replaced must never come back on this element —
    // that was exactly the boundary leak (cmw-app-chrome-reskin-fix). Checked as exact class-list
    // tokens (not substring matches) since the frozen preview's own font-variable class names
    // legitimately contain the substring "font-serif" (e.g. "mock-var--preview-font-serif").
    expect(preview).not.toHaveClass("font-serif");
    expect(preview).not.toHaveClass("bg-background");
    expect(preview).not.toHaveClass("text-primary");
  });

  it("loads the preview's own font variables, decoupled from the app chrome's --font-serif/--font-sans", () => {
    render(<DraftView draftHtml={DRAFT_HTML} revision="abc123" />);
    const heading = screen.getByRole("heading", { name: /why data-centre diversification matters/i });
    const preview = heading.closest("div");
    // The mocked next/font/google (vitest.setup.ts) echoes back the requested `variable` name —
    // asserting it here proves this component asked for its OWN preview-scoped variable, not the
    // chrome's, so the two can never collide or drift together.
    expect(preview?.className).toMatch(/mock-var--preview-font-serif/);
    expect(preview?.className).toMatch(/mock-var--preview-font-sans/);
    expect(preview?.className).not.toMatch(/mock-var--font-serif\b/);
    expect(preview?.className).not.toMatch(/mock-var--font-sans\b/);
  });

  it("keeps the editorial block on the app's own warning tokens — it never reaches a real reader", () => {
    render(<DraftView draftHtml={DRAFT_HTML} revision="abc123" />);
    const editorialHeading = screen.getByRole("heading", { name: /open items/i });
    const editorialBlock = editorialHeading.closest("div")?.parentElement;
    expect(editorialBlock?.className).toMatch(/border-warning/);
    expect(editorialBlock?.className).toMatch(/bg-warning/);
    expect(screen.getByText(/\[GAP: need a named customer quote\]/)).toBeInTheDocument();
  });

  it("shows a short, tweet-sized draft in full, expanded by default, with no clamp/modal control", () => {
    render(<DraftView draftHtml={TWEET_HTML} revision="abc123" />);
    const preview = document.querySelector(".piece-content-preview");
    expect(preview).toHaveTextContent(
      /three customer conversations converged on the same theme this week/i,
    );
    expect(screen.queryByRole("button", { name: /read full draft/i })).not.toBeInTheDocument();
  });

  it("shows a long draft immediately on landing, clamped, without needing to expand", () => {
    render(<DraftView draftHtml={LONG_HTML} revision="rev-9" />);
    expect(screen.getByRole("heading", { name: /a much longer, complex piece/i })).toBeInTheDocument();
    expect(screen.getAllByText("rev-9").length).toBeGreaterThan(0);
    expect(screen.getByText("long")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /read full draft/i })).toBeInTheDocument();
  });

  it("keeps an excerpt of what the piece says visible after the body is collapsed", () => {
    render(<DraftView draftHtml={LONG_HTML} revision="rev-9" />);
    fireEvent.click(screen.getByRole("button", { name: /show less.*current content/i }));
    expect(screen.queryByRole("heading", { name: /a much longer, complex piece/i })).not.toBeInTheDocument();
    // Collapsed, the summary excerpt is the only remaining answer to "is there a draft?".
    expect(screen.getByText(/A Much Longer, Complex Piece/)).toBeInTheDocument();
    expect(screen.getByText("rev-9")).toBeInTheDocument();
  });

  it("opens a modal with the full text from the clamped preview", () => {
    render(<DraftView draftHtml={LONG_HTML} revision="rev-9" />);
    const openModal = screen.getByRole("button", { name: /read full draft/i });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    fireEvent.click(openModal);
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText(/paragraph 39:/i)).toBeInTheDocument();
  });

  it("keeps the editorial GAP block visible even after the user collapses the body", () => {
    const longWithGaps = LONG_HTML.replace(
      "</body></html>",
      '<section class="editorial"><h3>Open items</h3><p>[GAP: still missing]</p></section></body></html>',
    );
    render(<DraftView draftHtml={longWithGaps} revision="rev-9" />);
    fireEvent.click(screen.getByRole("button", { name: /show less.*current content/i }));
    expect(screen.queryByRole("heading", { name: /a much longer, complex piece/i })).not.toBeInTheDocument();
    expect(screen.getByText(/\[GAP: still missing\]/)).toBeInTheDocument();
  });

  it("renders a brain-authored HTML fragment with no html/body wrapper", () => {
    const fragment =
      "<h1>Amazon QuickSight + Hendo</h1><p>A seller brief for the AWS x Hendo motion.</p>";
    render(<DraftView draftHtml={fragment} revision="abc123" brainSynced />);
    const heading = screen.getByRole("heading", { name: /amazon quicksight \+ hendo/i });
    expect(heading.closest(".piece-content-preview")).toHaveTextContent(
      /seller brief for the aws x hendo motion/i,
    );
    expect(screen.getByText("brain draft")).toBeInTheDocument();
  });

  describe("claim-level citation chips + sources drawer", () => {
    const CITED_HTML = `<html><body>
<p>A factual claim.<sup class="fn"><a href="#src1" id="r1">1</a></sup></p>
<ol><li id="src1">The origin call.</li></ol>
</body></html>`;
    const SOURCES: EvidenceSource[] = [
      { id: "src1", kind: "footnote", chip: "1", label: "The origin call.", urls: [], section: null },
    ];
    const CITATIONS: EvidenceCitation[] = [{ chip: "1", source_id: "src1", anchor_id: "r1" }];

    it("shows the chips inline by default and the drawer collapsed with its count", () => {
      render(
        <DraftView draftHtml={CITED_HTML} revision="abc123" sources={SOURCES} citations={CITATIONS} />,
      );
      // The chip stays in the draft body — that's the "by default" face.
      expect(screen.getByRole("link", { name: "1" })).toBeInTheDocument();
      expect(screen.getByText(/1 claim chip · 1 source/i)).toBeInTheDocument();
      expect(screen.queryByTestId("sources-drawer-body")).not.toBeInTheDocument();
    });

    it("opens the drawer and highlights the source when a chip is clicked", () => {
      render(
        <DraftView draftHtml={CITED_HTML} revision="abc123" sources={SOURCES} citations={CITATIONS} />,
      );
      fireEvent.click(screen.getByRole("link", { name: "1" }));
      expect(screen.getByTestId("sources-drawer-body")).toBeInTheDocument();
      const entry = screen.getByTestId("source-entry-src1");
      expect(entry.className).toMatch(/border-warning/);
    });

    it("leaves anchors that don't reference a known source to their native behavior", () => {
      const html = '<html><body><p><a href="#somewhere">jump</a></p></body></html>';
      render(
        <DraftView draftHtml={html} revision="r1" sources={SOURCES} citations={CITATIONS} />,
      );
      fireEvent.click(screen.getByRole("link", { name: "jump" }));
      expect(screen.queryByTestId("sources-drawer-body")).not.toBeInTheDocument();
    });

    it("renders no drawer at all for a piece without evidence annotations", () => {
      render(<DraftView draftHtml={TWEET_HTML} revision="abc123" />);
      expect(screen.queryByText(/sources & retrieval/i)).not.toBeInTheDocument();
    });
  });
});
