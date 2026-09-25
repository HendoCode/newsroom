import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { SourcesDrawer } from "@/components/piece-detail/sources-drawer";
import type { EvidenceCitation, EvidenceSource } from "@/lib/pieces/types";

// jsdom has no real layout engine, so scrollIntoView isn't implemented at all (same stub as
// source-registry.test.tsx).
Element.prototype.scrollIntoView = vi.fn();

const SOURCES: EvidenceSource[] = [
  { id: "src1", kind: "footnote", chip: "1", label: "The origin call.", urls: [], section: null },
  {
    id: "src2",
    kind: "footnote",
    chip: "2",
    label: "AWS docs.",
    urls: ["https://docs.aws.amazon.com/x"],
    section: null,
  },
  {
    id: "sources-md-1",
    kind: "sources-md",
    chip: null,
    label: "CloudWatch OTLP endpoints",
    urls: ["https://docs.aws.amazon.com/otlp.html"],
    section: "Research citations",
  },
];

const CITATIONS: EvidenceCitation[] = [
  { chip: "1", source_id: "src1", anchor_id: "r1" },
  { chip: "2", source_id: "src2", anchor_id: "r2" },
];

describe("SourcesDrawer", () => {
  it("renders nothing when the piece has no evidence at all", () => {
    const { container } = render(
      <SourcesDrawer sources={[]} citations={[]} openSignal={{ seq: 0, sourceId: null }} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("starts collapsed, showing the source count", () => {
    render(<SourcesDrawer sources={SOURCES} citations={CITATIONS} openSignal={{ seq: 0, sourceId: null }} />);
    // Both the toggle's sr-only label and the visible title carry the name.
    expect(screen.getAllByText(/sources & retrieval/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/2 claim chips · 3 sources/i)).toBeInTheDocument();
    expect(screen.queryByTestId("sources-drawer-body")).not.toBeInTheDocument();
  });

  it("expands into the full list: footnote group, then sources.md grouped by section", () => {
    render(<SourcesDrawer sources={SOURCES} citations={CITATIONS} openSignal={{ seq: 0, sourceId: null }} />);
    fireEvent.click(screen.getByRole("button", { name: /show more details — sources & retrieval/i }));
    const body = screen.getByTestId("sources-drawer-body");
    expect(body).toHaveTextContent("Cited in the draft");
    expect(body).toHaveTextContent("Research citations");
    expect(body).toHaveTextContent("The origin call.");
    expect(body).toHaveTextContent("CloudWatch OTLP endpoints");
    // External links render as real anchors.
    const link = screen.getByRole("link", { name: "https://docs.aws.amazon.com/x" });
    expect(link).toHaveAttribute("target", "_blank");
  });

  it("opens and highlights the matching entry when a draft chip click signals it", () => {
    // DraftView bumps the signal when a chip is clicked; mounting with a fresh non-zero signal
    // (the page landing straight on a chip target) must open and highlight without a click.
    const view = render(
      <SourcesDrawer sources={SOURCES} citations={CITATIONS} openSignal={{ seq: 1, sourceId: "src2" }} />,
    );
    expect(view.container.querySelector('[data-testid="sources-drawer-body"]')).toBeInTheDocument();
    const entry = view.container.querySelector('[data-testid="source-entry-src2"]');
    expect(entry?.className).toMatch(/border-warning/);
    // Sibling entries stay unhighlighted.
    const sibling = view.container.querySelector('[data-testid="source-entry-src1"]');
    expect(sibling?.className).not.toMatch(/border-warning/);
  });

  it("links a chip badge back to the claim's in-draft anchor", () => {
    render(<SourcesDrawer sources={SOURCES} citations={CITATIONS} openSignal={{ seq: 0, sourceId: null }} />);
    fireEvent.click(screen.getByRole("button", { name: /show more details — sources & retrieval/i }));
    const backLink = screen.getByRole("link", { name: "2" });
    expect(backLink).toHaveAttribute("href", "#r2");
  });
});
