import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ReviewRoundView } from "@/components/review-round/review-round-view";
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

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ReviewRoundView — round as primary UI object, doc as child link", () => {
  it("renders the round as the primary container with the doc as a child link", () => {
    vi.stubGlobal("fetch", vi.fn());
    render(
      <ReviewRoundView
        initial={piece({
          review_round: {
            round_number: 2,
            minted_from_revision: "rev-7",
            status: "open",
            share_mode: "internal",
            doc_url: "https://docs.google.com/document/d/abc123",
            opened_at: "2026-07-28T00:00:00Z",
            routing_log: [],
          },
        })}
      />,
    );

    // The round is the primary object — "Round 2" appears in both the round card title
    // and the stage badge; either is fine, the point is it's visibly present.
    const roundLabels = screen.getAllByText(/round 2/i);
    expect(roundLabels.length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/^open$/i)).toBeInTheDocument();

    // The Doc is a child link inside the round card
    expect(screen.getByRole("link", { name: /open doc in google docs/i })).toHaveAttribute(
      "href",
      "https://docs.google.com/document/d/abc123",
    );

    // Mint + Reviews-done panels still present
    expect(screen.getByRole("button", { name: /mint review doc/i })).toBeEnabled();
    expect(screen.getByRole("button", { name: /preview what will fold in/i })).toBeEnabled();

    // All rounds history is visible
    expect(screen.getByText(/all rounds/i)).toBeInTheDocument();

    // Finalize link still present
    expect(screen.getByRole("link", { name: /^finalize$/i })).toHaveAttribute(
      "href",
      "/pieces/p1/finalize",
    );
  });

  it('shows "no review round yet" when no round has been minted', () => {
    vi.stubGlobal("fetch", vi.fn());
    render(<ReviewRoundView initial={piece({ review_round: null })} />);

    expect(screen.getByText(/no review round yet/i)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /open doc/i })).not.toBeInTheDocument();
  });

  it("disables both panels and explains why outside the review stage", () => {
    vi.stubGlobal("fetch", vi.fn());
    render(<ReviewRoundView initial={piece({ stage: "incorporating" })} />);
    expect(screen.getByRole("button", { name: /mint review doc/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /preview what will fold in/i })).toBeDisabled();
    expect(screen.getByText(/only available from/i)).toBeInTheDocument();
  });
});
