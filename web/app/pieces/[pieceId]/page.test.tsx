import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { PieceDetail } from "@/lib/pieces/types";
import type { Spike } from "@/lib/spikes/types";

vi.mock("@/lib/session", () => ({
  requireUser: vi.fn().mockResolvedValue({ email: "you@company", name: null, image: null }),
}));

// Avoid loading the real NextAuth wiring (`@/auth`, pulled in transitively via `AppShell` ->
// `UserMenu` -> `@/lib/auth-actions`) — jsdom can't resolve next-auth's server-only internals,
// same reasoning as `app/signin/page.test.tsx`.
vi.mock("@/lib/auth-actions", () => ({
  signInWithIdentity: vi.fn(),
  signInWithGoogle: vi.fn(),
  signOutAction: vi.fn(),
}));

const {
  fetchPieceDetail,
  fetchTranscriptTurns,
  fetchPersonas,
  fetchSpike,
  AgentsRequestError,
} = vi.hoisted(() => {
  class AgentsRequestErrorImpl extends Error {
    constructor(public readonly status: number, message: string) {
      super(message);
    }
  }
  return {
    fetchPieceDetail: vi.fn(),
    fetchTranscriptTurns: vi.fn().mockResolvedValue([]),
    fetchPersonas: vi.fn().mockResolvedValue({ personas: [] }),
    fetchSpike: vi.fn(),
    AgentsRequestError: AgentsRequestErrorImpl,
  };
});
vi.mock("@/lib/agents-client", () => ({
  fetchPieceDetail,
  fetchTranscriptTurns,
  fetchPersonas,
  fetchSpike,
  AgentsRequestError,
}));

import PieceDetailPage from "@/app/pieces/[pieceId]/page";

function piece(overrides: Partial<PieceDetail> = {}): PieceDetail {
  return {
    id: "p1",
    slug: "p1",
    title: "A piece",
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

function spike(overrides: Partial<Spike> = {}): Spike {
  return {
    id: "spike-1",
    headline: "A spike",
    status: "picked",
    convergence_score: null,
    creator: "you@company",
    origin: { kind: "narrative", ref: "narrative-1" },
    source_ids: [],
    customer_partner: null,
    outcome_metric: null,
    rank_rationale: null,
    convergence_note: null,
    intent: null,
    piece_id: "p1",
    updated_at: null,
    ...overrides,
  };
}

afterEach(() => {
  vi.clearAllMocks();
  fetchTranscriptTurns.mockResolvedValue([]);
  fetchPersonas.mockResolvedValue({ personas: [] });
});

describe("PieceDetailPage — surfacing the originating narrative (cmw-archive-piece)", () => {
  it("resolves origin_spike_id -> a narrative-origin spike and renders the narrative reveal", async () => {
    fetchPieceDetail.mockResolvedValue(piece({ origin_spike_id: "spike-1" }));
    fetchSpike.mockResolvedValue(spike());

    render(await PieceDetailPage({ params: Promise.resolve({ pieceId: "p1" }) }));

    expect(fetchSpike).toHaveBeenCalledWith("spike-1");
    expect(
      screen.getByRole("button", { name: /view the narrative that started this piece/i }),
    ).toBeInTheDocument();
  });

  it("renders no narrative reveal when the piece has no origin spike at all", async () => {
    fetchPieceDetail.mockResolvedValue(piece({ origin_spike_id: null }));

    render(await PieceDetailPage({ params: Promise.resolve({ pieceId: "p1" }) }));

    expect(fetchSpike).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: /narrative/i })).not.toBeInTheDocument();
  });

  it("renders no narrative reveal when the origin spike wasn't seeded from a narrative", async () => {
    fetchPieceDetail.mockResolvedValue(piece({ origin_spike_id: "spike-1" }));
    fetchSpike.mockResolvedValue(spike({ origin: { kind: "oracle-run", ref: "job-1" } }));

    render(await PieceDetailPage({ params: Promise.resolve({ pieceId: "p1" }) }));

    expect(screen.queryByRole("button", { name: /narrative/i })).not.toBeInTheDocument();
  });

  it("degrades gracefully (no error page) when the origin spike can't be fetched", async () => {
    fetchPieceDetail.mockResolvedValue(piece({ origin_spike_id: "spike-1" }));
    fetchSpike.mockRejectedValue(new AgentsRequestError(404, "no spike 'spike-1'"));

    render(await PieceDetailPage({ params: Promise.resolve({ pieceId: "p1" }) }));

    expect(screen.getByText("A piece")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /narrative/i })).not.toBeInTheDocument();
  });
});

describe("PieceDetailPage — staleness triage (cmw-staleness-timestamps)", () => {
  it("shows both updated and human-touch relative times in the header meta line", async () => {
    const now = new Date();
    fetchPieceDetail.mockResolvedValue(
      piece({
        updated_at: new Date(now.getTime() - 60 * 60 * 1000).toISOString(), // 1h ago
        last_human_touch_at: new Date(now.getTime() - 5 * 60 * 1000).toISOString(), // 5m ago
      }),
    );

    render(await PieceDetailPage({ params: Promise.resolve({ pieceId: "p1" }) }));

    expect(screen.getByText("updated")).toBeInTheDocument();
    expect(screen.getByText("last action")).toBeInTheDocument();
    expect(screen.getByText(/^\d+m ago$/)).toBeInTheDocument(); // the human-touch value
  });

  it('shows "never" for a piece with no recorded human touch — a piece stuck since before an interview was ever answered', async () => {
    fetchPieceDetail.mockResolvedValue(piece({ last_human_touch_at: null }));

    render(await PieceDetailPage({ params: Promise.resolve({ pieceId: "p1" }) }));

    expect(screen.getByText("never")).toBeInTheDocument();
    expect(screen.getByText("never")).toHaveClass("text-warning");
  });
});
