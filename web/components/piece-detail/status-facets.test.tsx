import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StatusFacets } from "@/components/piece-detail/status-facets";
import type { PieceDetail } from "@/lib/pieces/types";

function piece(overrides: Partial<PieceDetail> = {}): PieceDetail {
  return {
    id: "p1",
    slug: "token-vs-storage",
    title: "token-vs-storage",
    voice: "demo-mira",
    stage: "review",
    owner: null,
    assigned_experts: [],
    origin_spike_id: null,
    target: null,
    partners: [],
    open_gaps: 0,
    open_clearances: 0,
    latest_revision: "abc1234def",
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

describe("StatusFacets", () => {
  it("renders all six facets as one labeled strip, not one flattened status", () => {
    render(<StatusFacets piece={piece()} />);
    const strip = screen.getByRole("group", { name: /piece status facets/i });
    expect(strip).toBeInTheDocument();
    for (const label of ["Stage", "Execution", "Review", "Attention", "Lineage", "Learning"]) {
      expect(strip).toHaveTextContent(label);
    }
    // Six distinct clickable facets.
    expect(screen.getAllByRole("button").length).toBe(6);
  });

  it("carries the compact read-outs per facet", () => {
    render(<StatusFacets piece={piece()} />);
    expect(screen.getByTestId("facet-value-stage")).toHaveTextContent("Review");
    expect(screen.getByTestId("facet-value-execution")).toHaveTextContent("idle");
    expect(screen.getByTestId("facet-value-review")).toHaveTextContent("no council yet");
    expect(screen.getByTestId("facet-value-attention")).toHaveTextContent("clear");
    expect(screen.getByTestId("facet-value-lineage")).toHaveTextContent("rev abc1234");
    expect(screen.getByTestId("facet-value-learning")).toHaveTextContent("none yet");
  });

  it("flags attention as open (and lists what is owed) when humans owe the piece", () => {
    render(
      <StatusFacets
        piece={
          piece({
            open_gaps: 2,
            open_clearances: 1,
            interviews: [
              { interview_id: "i1", assigned_expert: "sam", status: "open", about: null, is_gap_interview: false },
            ],
          })
        }
      />,
    );
    expect(screen.getByTestId("facet-value-attention")).toHaveTextContent("4 open");
    fireEvent.click(screen.getByRole("button", { name: /attention/i }));
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveTextContent(/open GAPs/i);
    expect(dialog).toHaveTextContent("resume (sam)");
  });

  it("flags execution as failed and shows the flagged failure in the drawer", () => {
    render(
      <StatusFacets
        piece={
          piece({
            failures: [
              {
                type: "finalize",
                code: "render-failed",
                message: "chromium exited",
                triggered_by: null,
                retryable: true,
                cost: 0.02,
              },
            ],
          })
        }
      />,
    );
    expect(screen.getByTestId("facet-value-execution")).toHaveTextContent("1 failed");
    fireEvent.click(screen.getByRole("button", { name: /execution/i }));
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveTextContent("finalize");
    expect(dialog).toHaveTextContent("render-failed");
    expect(dialog).toHaveTextContent("chromium exited");
  });

  it("shows the council aggregate on the review facet and the record in its drawer", () => {
    render(
      <StatusFacets
        piece={
          piece({
            council: {
              round_number: 2,
              iteration: 1,
              revision: "rev-9",
              aggregate: 9,
              cost: 0.12,
              stop_reason: null,
              stop_message: null,
              editor_scores: [
                {
                  editor: "slop-allergist",
                  score: 9,
                  mandatory: true,
                  editorial_fixes: [],
                  information_gaps: [],
                  clearances: [],
                  hard_cap_applied: false,
                },
              ],
            },
          })
        }
      />,
    );
    expect(screen.getByTestId("facet-value-review")).toHaveTextContent("9.0 · r2");
    fireEvent.click(screen.getByRole("button", { name: /^review/i }));
    expect(screen.getByRole("dialog")).toHaveTextContent("slop-allergist");
  });

  it("shows pending lessons on the learning facet", () => {
    render(
      <StatusFacets
        piece={
          piece({
            lessons: [
              { id: "l1", observed_change: "x", generalizable_rule: "Prefer concrete numbers.", status: "proposed" },
            ],
          })
        }
      />,
    );
    expect(screen.getByTestId("facet-value-learning")).toHaveTextContent("1 to decide");
    fireEvent.click(screen.getByRole("button", { name: /learning/i }));
    expect(screen.getByRole("dialog")).toHaveTextContent("Prefer concrete numbers.");
    expect(screen.getByRole("dialog")).toHaveTextContent(/voice kit/i);
  });

  it("keeps the stage facet's round visible for loop stages", () => {
    render(
      <StatusFacets
        piece={
          piece({
            stage: "council",
            review_round: {
              round_number: 3,
              minted_from_revision: "rev-1",
              status: "open",
              share_mode: "internal",
              doc_url: null,
              opened_at: null,
              routing_log: [],
            },
          })
        }
      />,
    );
    expect(screen.getByTestId("facet-value-stage")).toHaveTextContent("round 3");
  });
});
