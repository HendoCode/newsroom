import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StageBadge } from "@/components/dashboard/stage-badge";

describe("StageBadge — round number on every review-loop stage, not just review", () => {
  it("shows the round on review", () => {
    render(<StageBadge stage="review" round={3} />);
    expect(screen.getByText("Review · round 3")).toBeInTheDocument();
  });

  it("shows the round on council mid-loop", () => {
    render(<StageBadge stage="council" round={2} />);
    expect(screen.getByText("Council · round 2")).toBeInTheDocument();
  });

  it("shows the round on incorporating mid-loop", () => {
    render(<StageBadge stage="incorporating" round={3} />);
    expect(screen.getByText("Incorporating · round 3")).toBeInTheDocument();
  });

  it("never shows a round outside the review loop, even if one is passed", () => {
    render(<StageBadge stage="finalized" round={2} />);
    expect(screen.getByText("Finalized")).toBeInTheDocument();
    expect(screen.queryByText(/round/)).not.toBeInTheDocument();
  });

  it("omits the round entirely when there isn't one yet", () => {
    render(<StageBadge stage="review" round={null} />);
    expect(screen.getByText("Review")).toBeInTheDocument();
  });
});
