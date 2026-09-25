import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { BetweenRoundsLog } from "@/components/piece-detail/between-rounds-log";
import type { ReviewRoundRecord } from "@/lib/pieces/types";

function round(overrides: Partial<ReviewRoundRecord> = {}): ReviewRoundRecord {
  return {
    round_number: 1,
    minted_from_revision: "rev-1",
    status: "open",
    share_mode: "internal",
    doc_url: null,
    opened_at: null,
    routing_log: [],
    ...overrides,
  };
}

describe("BetweenRoundsLog", () => {
  it("shows a fallback when the piece has never had a review round", () => {
    render(<BetweenRoundsLog rounds={[]} />);
    expect(screen.getByText(/no review rounds opened yet/i)).toBeInTheDocument();
  });

  it("sorts most-recent round first and shows each round's own routing-log lines", () => {
    render(
      <BetweenRoundsLog
        rounds={[
          round({ round_number: 1, status: "archived", routing_log: ["clearance routed to owner a@x.com: 'ok?'"] }),
          round({ round_number: 2, status: "open" }),
        ]}
      />,
    );
    const headings = screen.getAllByText(/^Round \d$/);
    expect(headings.map((h) => h.textContent)).toEqual(["Round 2", "Round 1"]);
    expect(screen.getByText(/clearance routed to owner/i)).toBeInTheDocument();
    expect(screen.getByText(/no feedback routed in this round yet/i)).toBeInTheDocument();
  });
});
