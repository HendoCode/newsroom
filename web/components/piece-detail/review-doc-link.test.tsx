import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ReviewDocLink } from "@/components/piece-detail/review-doc-link";
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

describe("ReviewDocLink", () => {
  it("renders a prominent, new-tab link to the current round's Doc when one exists", () => {
    render(
      <ReviewDocLink
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

    const link = screen.getByRole("link", { name: /open review doc/i });
    expect(link).toHaveAttribute("href", "https://docs.google.com/document/d/abc123");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", expect.stringContaining("noopener"));
  });

  it("falls back to a subtle note when in review but no Doc link exists yet", () => {
    render(<ReviewDocLink piece={piece({ review_round: null })} />);

    expect(screen.queryByRole("link", { name: /open review doc/i })).not.toBeInTheDocument();
    expect(screen.getByText(/no open review doc yet/i)).toBeInTheDocument();
  });

  it("falls back to a subtle note when the round exists but doc_url is not populated", () => {
    render(
      <ReviewDocLink
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

    expect(screen.queryByRole("link", { name: /open review doc/i })).not.toBeInTheDocument();
    expect(screen.getByText(/no open review doc yet/i)).toBeInTheDocument();
  });

  it("renders nothing outside the review stage, even if a doc_url is present", () => {
    const { container } = render(
      <ReviewDocLink
        piece={piece({
          stage: "finalized",
          review_round: {
            round_number: 2,
            minted_from_revision: "rev-7",
            status: "archived",
            share_mode: "internal",
            doc_url: "https://docs.google.com/document/d/abc123",
            opened_at: "2026-07-28T00:00:00Z",
            routing_log: [],
          },
        })}
      />,
    );

    expect(container).toBeEmptyDOMElement();
  });
});
