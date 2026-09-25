import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Dashboard } from "@/components/dashboard/dashboard";
import type { DashboardResponse, PieceStage, QueueItem } from "@/lib/dashboard/types";

const ME = "you@company";
const OTHER = "someone@example.com";

function pieceItem(overrides: Partial<QueueItem> = {}): QueueItem {
  return {
    kind: "piece",
    id: Math.random().toString(36).slice(2),
    title: "A piece",
    voice: "demo-mira",
    stage: "review",
    spike_status: null,
    owner: ME,
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

function spikeItem(overrides: Partial<QueueItem> = {}): QueueItem {
  return pieceItem({
    kind: "spike",
    title: "A spike",
    voice: null,
    stage: null,
    spike_status: "picked",
    owner: null,
    creator: ME,
    spike_assigned: false,
    ...overrides,
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

/** A queue exercising all three sections: a decision, a running job, and terminal library pieces. */
function fullQueue(): QueueItem[] {
  return [
    pieceItem({ id: "review-piece", title: "Review piece", stage: "review", owner: ME }),
    pieceItem({ id: "incorp-piece", title: "Incorporating piece", stage: "incorporating", owner: ME }),
    pieceItem({ id: "published-piece", title: "Published piece", stage: "published", owner: OTHER }),
    pieceItem({
      id: "failed-piece",
      title: "Failed piece",
      stage: "interviewing",
      owner: OTHER,
      failed_job: { type: "draft", code: "boom", message: "broke", triggered_by: ME, retryable: true, cost: 0 },
    }),
    spikeItem({ id: "picked-spike", title: "Picked spike" }),
  ];
}

describe("Dashboard — the three desk sections replace the five tabs", () => {
  it("renders Inbox / Machine working / Library and none of the old tab chrome", () => {
    render(<Dashboard initial={{ source: "store", items: fullQueue() }} email={ME} />);

    expect(screen.getByRole("heading", { name: "Inbox" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /machine working/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Library" })).toBeInTheDocument();

    // The five saved-filter tabs (and the Sources interstitial) are gone entirely.
    expect(screen.queryByRole("tablist")).toBeNull();
    for (const gone of ["Needs my action", "My pieces", "All in flight", "Spikes & Vault", "Sources have their own screen"]) {
      expect(screen.queryByText(gone)).toBeNull();
    }
  });
});

describe("Dashboard — Inbox groups only human-actionable decisions by decision type", () => {
  it("groups the queue's predicate hits under their decision headings", () => {
    render(<Dashboard initial={{ source: "store", items: fullQueue() }} email={ME} />);

    // review-piece (owner in review) → "Review / close a round"; failed-piece (my failed job) →
    // "Recover a failure"; picked-spike → "Pick a spike". Pieces also render once more in the
    // Library (spikes never do), hence the 2-vs-1 title counts.
    expect(screen.getByText("Review / close a round")).toBeInTheDocument();
    expect(screen.getByText("Recover a failure")).toBeInTheDocument();
    expect(screen.getByText("Pick a spike")).toBeInTheDocument();
    expect(screen.getAllByText("Review piece")).toHaveLength(2);
    expect(screen.getAllByText("Failed piece")).toHaveLength(2);
    expect(screen.getAllByText("Picked spike")).toHaveLength(1);
    expect(screen.getByText("3 decisions need you")).toBeInTheDocument();
  });

  it("shows the honest empty state when nothing is attributed to you", () => {
    render(
      <Dashboard
        initial={{ source: "store", items: [pieceItem({ owner: OTHER, stage: "drafting" })] }}
        email={ME}
      />,
    );
    expect(screen.getByText("Nothing needs you right now")).toBeInTheDocument();
    expect(screen.getByText("nothing needs you")).toBeInTheDocument();
  });
});

describe("Dashboard — Machine strip is ambient visibility, not a queue", () => {
  it("shows the running piece on the strip and NOT in the Inbox (a running job is not a decision)", () => {
    render(<Dashboard initial={{ source: "store", items: fullQueue() }} email={ME} />);

    const strip = screen.getByRole("region", { name: /machine working/i });
    expect(within(strip).getByText("Incorporating piece")).toBeInTheDocument();
    expect(within(strip).getByText(/1 piece in motion/)).toBeInTheDocument();

    // The predicate DOES match the owner of an incorporating piece ("wait for it, or check in"),
    // but that is machine movement — the Inbox count proves it stayed out of the decisions.
    expect(screen.getByText("3 decisions need you")).toBeInTheDocument();
    expect(screen.queryByText(/Incorporating review feedback|wait for it/i)).toBeNull();
  });

  it("renders no clickable links for running pieces — visibility only", () => {
    render(<Dashboard initial={{ source: "store", items: fullQueue() }} email={ME} />);
    const strip = screen.getByRole("region", { name: /machine working/i });
    expect(within(strip).queryAllByRole("link")).toHaveLength(0);
    expect(within(strip).queryAllByRole("button")).toHaveLength(0);
  });

  it("reports idle when nothing is running", () => {
    render(
      <Dashboard
        initial={{ source: "store", items: [pieceItem({ stage: "review" })] }}
        email={ME}
      />,
    );
    const strip = screen.getByRole("region", { name: /machine working/i });
    expect(within(strip).getByText("idle")).toBeInTheDocument();
    expect(within(strip).getByText(/Nothing is in motion right now/)).toBeInTheDocument();
  });
});

describe("Dashboard — Library is every piece across every stage, honest about terminal states", () => {
  it("lists a piece at every stage, including published and finalized", () => {
    const stages: PieceStage[] = [
      "interviewing",
      "drafting",
      "council",
      "review",
      "incorporating",
      "finalizing",
      "finalized",
      "lessons",
      "paused",
      "published",
    ];
    const items = stages.map((stage) =>
      pieceItem({ id: stage, title: `${stage} piece`, stage, owner: OTHER }),
    );
    render(<Dashboard initial={{ source: "store", items }} email={ME} />);
    const library = screen.getByRole("region", { name: "Library" });
    for (const stage of stages) {
      expect(within(library).getByText(`${stage} piece`)).toBeInTheDocument();
    }
    expect(library).toHaveAttribute("id", "library");
  });

  it("lists terminal pieces too and names the in-flight / done / failed split", () => {
    render(<Dashboard initial={{ source: "store", items: fullQueue() }} email={ME} />);

    const library = screen.getByRole("region", { name: "Library" });
    // Every piece is here regardless of stage — including published — and the spike is not.
    expect(within(library).getByText("Review piece")).toBeInTheDocument();
    expect(within(library).getByText("Incorporating piece")).toBeInTheDocument();
    expect(within(library).getByText("Published piece")).toBeInTheDocument();
    expect(within(library).getByText("Failed piece")).toBeInTheDocument();
    expect(within(library).queryByText("Picked spike")).toBeNull();

    // 4 pieces: review + incorporating in flight, published done, failed failed.
    expect(within(library).getByText("4 pieces · 2 in flight · 1 done · 1 failed")).toBeInTheDocument();
  });

  it("filters only the Library, never the Inbox or the strip", () => {
    render(<Dashboard initial={{ source: "store", items: fullQueue() }} email={ME} />);

    fireEvent.change(screen.getByLabelText("Voice"), { target: { value: "demo-dana" } });

    // No piece in the fixture is voice=demo-dana, so the Library narrows to nothing…
    expect(screen.getByText("No pieces match the current filters.")).toBeInTheDocument();
    // …while the Inbox and the strip are untouched by the Library's filter.
    expect(screen.getByText("3 decisions need you")).toBeInTheDocument();
    expect(screen.getByText("Incorporating piece")).toBeInTheDocument();
  });
});

describe("Dashboard — archiving from the list (triage at scale)", () => {
  it("posts /archive and removes the item from EVERY section without a full dashboard refetch", async () => {
    const initial: DashboardResponse = { source: "store", items: fullQueue() };
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/api/pieces/review-piece/archive") {
        expect(init?.method).toBe("POST");
        return new Response(JSON.stringify({ id: "review-piece", slug: "review-piece", archived_at: "2026-08-10T00:00:00Z" }), {
          status: 200,
        });
      }
      throw new Error(`unexpected fetch ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<Dashboard initial={initial} email={ME} />);

    // The seeded review+owner piece is both an inbox decision and a library row.
    expect(screen.getAllByText("Review piece")).toHaveLength(2);

    fireEvent.click(screen.getAllByRole("button", { name: /archive/i })[0]!);

    // All three sections derive from the one items state, so one archive removes it everywhere.
    await waitFor(() => expect(screen.queryAllByText("Review piece")).toHaveLength(0));
    expect(screen.getByText("2 decisions need you")).toBeInTheDocument();
    expect(screen.getByText("3 pieces · 1 in flight · 1 done · 1 failed")).toBeInTheDocument();
    // Optimistic local removal — never a second /api/dashboard round trip for this.
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("does not remove the item when the archive request fails", async () => {
    const initial: DashboardResponse = { source: "store", items: fullQueue() };
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ error: "boom" }), { status: 502 })));

    render(<Dashboard initial={initial} email={ME} />);
    fireEvent.click(screen.getAllByRole("button", { name: /archive/i })[0]!);

    await waitFor(() => expect(screen.getAllByText("Review piece")).toHaveLength(2));
  });
});

describe("Dashboard — refresh refetches the whole queue", () => {
  it("replaces the queue from /api/dashboard", async () => {
    const fetchMock = vi
      .fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>()
      .mockResolvedValue(
        new Response(
          JSON.stringify({ source: "store", items: [pieceItem({ id: "fresh", title: "Fresh piece", stage: "council" })] }),
          { status: 200 },
        ),
      );
    vi.stubGlobal("fetch", fetchMock);

    render(<Dashboard initial={{ source: "seed", items: [] }} email={ME} />);
    expect(screen.getByText("seeded data")).toBeInTheDocument();
    expect(screen.getByText(/Nothing is in motion right now/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /refresh/i }));

    await waitFor(() => expect(screen.getByText("live data")).toBeInTheDocument());
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe("/api/dashboard");
    // The fresh council piece lands on the machine strip and in the library.
    expect(screen.getAllByText("Fresh piece")).toHaveLength(2);
  });
});
