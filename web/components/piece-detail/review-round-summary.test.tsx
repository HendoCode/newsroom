import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ReviewRoundSummary } from "@/components/piece-detail/review-round-summary";
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
    latest_revision: null,
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

describe("ReviewRoundSummary — round as primary UI object, doc as child link", () => {
  it("shows the round as the primary object with the doc as a child link", () => {
    render(
      <ReviewRoundSummary
        piece={piece({
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

    // The round is the primary object
    expect(screen.getByText(/round 2/i)).toBeInTheDocument();
    expect(screen.getByText(/^open$/i)).toBeInTheDocument();
    expect(screen.getByText(/internal/i)).toBeInTheDocument();
    expect(screen.getByText(/rev-7/i)).toBeInTheDocument();

    // The Doc is a child link, not the primary button
    const docLink = screen.getByRole("link", { name: /open doc/i });
    expect(docLink).toHaveAttribute("href", "https://docs.google.com/document/d/abc123");
    expect(docLink).toHaveAttribute("target", "_blank");
    expect(docLink).toHaveAttribute("rel", expect.stringContaining("noopener"));

    // The "Manage round" link goes to the review round page
    expect(screen.getByRole("link", { name: /manage round/i })).toHaveAttribute(
      "href",
      "/pieces/p1/review",
    );
  });

  it('shows "no round yet" with a mint link when no round has been opened', () => {
    render(
      <ReviewRoundSummary
        piece={piece({ review_round: null })}
      />,
    );

    expect(screen.getByText(/no round yet/i)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /open doc/i })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /mint round/i })).toHaveAttribute(
      "href",
      "/pieces/p1/review",
    );
  });

  it("does not show a doc link when the round exists but doc_url is not populated", () => {
    render(
      <ReviewRoundSummary
        piece={piece({
          review_round: {
            round_number: 1,
            minted_from_revision: "rev-3",
            status: "open",
            share_mode: "internal",
            doc_url: null,
            opened_at: "2026-07-27T00:00:00Z",
            routing_log: [],
          },
        })}
      />,
    );

    expect(screen.getByText(/round 1/i)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /open doc/i })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /manage round/i })).toBeInTheDocument();
  });

  it("renders nothing outside the review stage", () => {
    const { container } = render(
      <ReviewRoundSummary
        piece={piece({ stage: "finalized" })}
      />,
    );

    expect(container).toBeEmptyDOMElement();
  });
});