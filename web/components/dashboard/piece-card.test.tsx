import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PieceCard } from "@/components/dashboard/piece-card";
import type { QueueItem } from "@/lib/dashboard/types";

function pieceItem(overrides: Partial<QueueItem> = {}): QueueItem {
  return {
    kind: "piece",
    id: "p1",
    title: "A piece",
    voice: "demo-mira",
    stage: "review",
    spike_status: null,
    owner: "you@company",
    assigned_experts: [],
    creator: null,
    council_aggregate: null,
    open_gaps: 0,
    open_clearances: 0,
    review_round: null,
    open_interviews: [],
    has_complete_interview: false,
    failed_job: null,
    lessons_proposed: 0,
    spike_assigned: false,
    updated_at: null,
    last_human_touch_at: null,
    ...overrides,
  };
}

describe("PieceCard — the per-item Archive action (triage at scale)", () => {
  it("renders no Archive button when onArchive is omitted", () => {
    render(<PieceCard item={pieceItem()} email="you@company" />);
    expect(screen.queryByRole("button", { name: /archive/i })).not.toBeInTheDocument();
  });

  it("renders no Archive button for a spike item, even when onArchive is provided", () => {
    render(
      <PieceCard
        item={{
          kind: "spike",
          id: "s1",
          title: "A spike",
          voice: null,
          stage: null,
          spike_status: "proposed",
          owner: null,
          assigned_experts: [],
          creator: "you@company",
          council_aggregate: null,
          open_gaps: 0,
          open_clearances: 0,
          review_round: null,
          open_interviews: [],
          has_complete_interview: false,
          failed_job: null,
          lessons_proposed: 0,
          spike_assigned: false,
          updated_at: null,
          last_human_touch_at: null,
        }}
        email="you@company"
        onArchive={vi.fn()}
      />,
    );
    expect(screen.queryByRole("button", { name: /archive/i })).not.toBeInTheDocument();
  });

  it("calls onArchive with the item when a piece's Archive button is clicked", async () => {
    const onArchive = vi.fn().mockResolvedValue(undefined);
    const item = pieceItem();
    render(<PieceCard item={item} email="you@company" onArchive={onArchive} />);

    fireEvent.click(screen.getByRole("button", { name: /archive/i }));

    await waitFor(() => expect(onArchive).toHaveBeenCalledWith(item));
  });

  it("does not gate the Archive button on stage — available for a published piece too", () => {
    render(<PieceCard item={pieceItem({ stage: "published" })} email="you@company" onArchive={vi.fn()} />);
    expect(screen.getByRole("button", { name: /archive/i })).toBeEnabled();
  });
});

describe("PieceCard — staleness triage (cmw-staleness-timestamps)", () => {
  const NOW = new Date("2026-08-11T12:00:00.000Z");

  it("shows both updated and human-touch relative times, in the always-visible collapsed line", () => {
    render(
      <PieceCard
        item={pieceItem({
          updated_at: new Date("2026-08-11T11:00:00.000Z").toISOString(),
          last_human_touch_at: new Date("2026-08-11T10:00:00.000Z").toISOString(),
        })}
        email="you@company"
        now={NOW}
      />,
    );
    expect(screen.getByText("updated")).toBeInTheDocument();
    expect(screen.getByText("1h ago")).toBeInTheDocument();
    expect(screen.getByText("human")).toBeInTheDocument();
    expect(screen.getByText("2h ago")).toBeInTheDocument();
  });

  it('shows "never" for a piece with no recorded human touch — the piece-stuck-in-interviewing case', () => {
    render(
      <PieceCard
        item={pieceItem({ last_human_touch_at: null })}
        email="you@company"
        now={NOW}
      />,
    );
    expect(screen.getByText("never")).toBeInTheDocument();
  });

  it("flags a human-cold piece (never touched, or touched over a week ago) with the warning token", () => {
    render(
      <PieceCard
        item={pieceItem({ last_human_touch_at: null })}
        email="you@company"
        now={NOW}
      />,
    );
    expect(screen.getByText("never")).toHaveClass("text-warning");
  });

  it("does not flag a recently human-touched piece", () => {
    render(
      <PieceCard
        item={pieceItem({ last_human_touch_at: new Date("2026-08-11T10:00:00.000Z").toISOString() })}
        email="you@company"
        now={NOW}
      />,
    );
    expect(screen.getByText("2h ago")).not.toHaveClass("text-warning");
  });

  it("never renders a human-touch fact for a spike (no human-touch tracking for spikes)", () => {
    render(
      <PieceCard
        item={{
          kind: "spike",
          id: "s1",
          title: "A spike",
          voice: null,
          stage: null,
          spike_status: "proposed",
          owner: null,
          assigned_experts: [],
          creator: "you@company",
          council_aggregate: null,
          open_gaps: 0,
          open_clearances: 0,
          review_round: null,
          open_interviews: [],
          has_complete_interview: false,
          failed_job: null,
          lessons_proposed: 0,
          spike_assigned: false,
          updated_at: new Date("2026-08-11T11:00:00.000Z").toISOString(),
          last_human_touch_at: null,
        }}
        email="you@company"
        now={NOW}
      />,
    );
    expect(screen.queryByText("human")).not.toBeInTheDocument();
    expect(screen.getByText("updated")).toBeInTheDocument(); // updated_at still shows for a spike
  });
});
