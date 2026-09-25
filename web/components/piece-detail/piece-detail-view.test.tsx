import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PieceDetailView } from "@/components/piece-detail/piece-detail-view";
import type { PieceDetail } from "@/lib/pieces/types";

function piece(overrides: Partial<PieceDetail> = {}): PieceDetail {
  return {
    id: "p1",
    slug: "token-vs-storage",
    title: "token-vs-storage",
    voice: "demo-mira",
    stage: "review",
    owner: "you@company",
    assigned_experts: [],
    origin_spike_id: null,
    target: null,
    partners: [],
    open_gaps: 0,
    open_clearances: 0,
    latest_revision: "rev-7",
    created_at: null,
    updated_at: null,
    last_human_touch_at: null,
    draft_html: null,
    brain_synced: false,
    council: null,
    review_round: null,
    review_rounds: [],
    interviews: [],
    failures: [],
    lessons: [],
    activity: [],
    final_doc: null,
    final_template_version: null,
    final_rendered_at: null,
    published_release: 0,
    published_html_url: null,
    published_pdf_url: null,
    published_doc: null,
    published_at: null,
    ...overrides,
  };
}

describe("PieceDetailView — current content is visible in-progress", () => {
  it("renders the draft body on landing so a user can see what the piece says", () => {
    render(
      <PieceDetailView
        initial={piece({
          draft_html:
            "<html><body><h1>Why Data-Centre Diversification Matters</h1><p>Three customer conversations converged on the same theme.</p></body></html>",
          latest_revision: "rev-7",
        })}
        initialTurns={[]}
      />,
    );
    const heading = screen.getByRole("heading", {
      name: /why data-centre diversification matters/i,
    });
    expect(heading.closest(".piece-content-preview")).toHaveTextContent(
      /three customer conversations converged/i,
    );
  });

  it("renders a brain-synced piece.md HTML fragment (no html/body wrapper) as the piece content", () => {
    render(
      <PieceDetailView
        initial={piece({
          title: "Amazon Quick + Hendo",
          brain_synced: true,
          latest_revision: "bf549f9",
          draft_html:
            "<h1>Amazon QuickSight + Hendo seller brief</h1><p>How Hendo lands inside Amazon QuickSight for the joint motion.</p>",
        })}
        initialTurns={[]}
      />,
    );
    const heading = screen.getByRole("heading", {
      name: /amazon quicksight \+ hendo seller brief/i,
    });
    expect(heading.closest(".piece-content-preview")).toHaveTextContent(
      /how hendo lands inside amazon quicksight/i,
    );
    expect(screen.getByText("brain draft")).toBeInTheDocument();
    expect(screen.queryByText(/no content yet/i)).not.toBeInTheDocument();
  });
});

describe("PieceDetailView — status facets", () => {
  it("shows the six status facets in the header instead of one flattened status badge", () => {
    render(<PieceDetailView initial={piece({ stage: "review" })} initialTurns={[]} />);
    const strip = screen.getByRole("group", { name: /piece status facets/i });
    expect(strip).toBeInTheDocument();
    for (const label of ["Stage", "Execution", "Review", "Attention", "Lineage", "Learning"]) {
      expect(strip).toHaveTextContent(label);
    }
  });
});

describe("PieceDetailView — post-publish Derivatives tab", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => [] }));
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("does not show the post-publish tablist while the piece is still in flight", () => {
    render(<PieceDetailView initial={piece({ stage: "review" })} initialTurns={[]} />);
    expect(screen.queryByRole("tablist", { name: /post-publish workspace/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Derivatives" })).not.toBeInTheDocument();
  });

  it("shows the Derivatives tab (selected) once the piece has published", () => {
    render(
      <PieceDetailView
        initial={piece({ stage: "published", published_release: 1 })}
        initialTurns={[]}
      />,
    );
    expect(screen.getByRole("tablist", { name: /post-publish workspace/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Derivatives" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel")).toHaveTextContent(/publish is not the last beat/i);
    expect(screen.getByRole("heading", { name: /creatable/i })).toBeInTheDocument();
  });
});

describe("PieceDetailView — seeded provenance survives the click-through (cmw-boss-facing-presentation, HIGH)", () => {
  it("shows the seeded-data badge with a how-to-make-it-real link on a seeded piece", () => {
    render(<PieceDetailView initial={piece({ seeded: true })} initialTurns={[]} />);
    expect(screen.getByTestId("seeded-data-badge")).toHaveTextContent("seeded data");
    expect(screen.getByRole("link", { name: /how do i make this real/i })).toHaveAttribute(
      "href",
      "/how-it-works",
    );
  });

  it("shows no seeded badge on a real (store-backed) piece", () => {
    render(<PieceDetailView initial={piece({ seeded: false })} initialTurns={[]} />);
    expect(screen.queryByTestId("seeded-data-badge")).not.toBeInTheDocument();
  });

  it("shows no seeded badge when the field is absent (older responses/fixtures)", () => {
    render(<PieceDetailView initial={piece()} initialTurns={[]} />);
    expect(screen.queryByTestId("seeded-data-badge")).not.toBeInTheDocument();
  });
});
