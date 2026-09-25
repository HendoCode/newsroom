import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Pipeline } from "@/components/piece-detail/pipeline";
import type { PieceDetail } from "@/lib/pieces/types";

function piece(overrides: Partial<PieceDetail> = {}): PieceDetail {
  return {
    id: "p1",
    slug: "token-vs-storage",
    title: "token-vs-storage",
    voice: "demo-mira",
    stage: "interviewing",
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

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Pipeline — the rail and the CTA, folded into one block (cmw-pipeline-depiction-design)", () => {
  it("posts the enough-input trigger, then refetches and reports the refreshed piece", async () => {
    const refreshed = piece({ stage: "council" });
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/api/pieces/p1/trigger") {
        expect(init?.method).toBe("POST");
        expect(JSON.parse(String(init?.body))).toEqual({ trigger: "enough-input" });
        return new Response(
          JSON.stringify({ id: "p1", slug: "token-vs-storage", stage: "council" }),
          { status: 200 },
        );
      }
      if (url === "/api/pieces/p1") {
        return new Response(JSON.stringify(refreshed), { status: 200 });
      }
      throw new Error(`unexpected fetch ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    const onUpdated = vi.fn();
    render(<Pipeline piece={piece()} onUpdated={onUpdated} />);

    fireEvent.click(screen.getByRole("button", { name: /enough input → draft/i }));

    await waitFor(() => expect(onUpdated).toHaveBeenCalledWith(refreshed));
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("shows an inline error and does not call onUpdated when the trigger is rejected", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      if (String(input) === "/api/pieces/p1/trigger") {
        return new Response(JSON.stringify({ error: "illegal transition interviewing → drafting" }), {
          status: 409,
        });
      }
      throw new Error("refetch should not happen after a failed trigger");
    });
    vi.stubGlobal("fetch", fetchMock);

    const onUpdated = vi.fn();
    render(<Pipeline piece={piece()} onUpdated={onUpdated} />);

    fireEvent.click(screen.getByRole("button", { name: /enough input → draft/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/illegal transition/i);
    expect(onUpdated).not.toHaveBeenCalled();
  });

  it("renders a non-actionable running state for a batch stage (no trigger button), the current rail node marked aria-current", () => {
    vi.stubGlobal("fetch", vi.fn());
    render(<Pipeline piece={piece({ stage: "council" })} onUpdated={vi.fn()} />);
    expect(screen.getByText(/council running…/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^council/i })).not.toBeInTheDocument();
    const current = screen.getByRole("listitem", { current: "step" });
    expect(current).toHaveTextContent("Council");
  });

  it("review stage's primary action is a LINK into the review-round screen, Finalize stays a distinct secondary LINK, pause a secondary button", () => {
    vi.stubGlobal("fetch", vi.fn());
    render(<Pipeline piece={piece({ stage: "review", id: "p1" })} onUpdated={vi.fn()} />);
    const reviewLink = screen.getByRole("link", { name: /open review round/i });
    expect(reviewLink).toHaveAttribute("href", "/pieces/p1/review");
    const finalizeLink = screen.getByRole("link", { name: /^finalize$/i });
    expect(finalizeLink).toHaveAttribute("href", "/pieces/p1/finalize");
    expect(screen.getByRole("button", { name: /stop for the day/i })).toBeInTheDocument();
  });

  it("review stage's 'Start another round of interviews' secondary action expands into the persona-picker form on click, collapsed by default", () => {
    vi.stubGlobal("fetch", vi.fn());
    render(
      <Pipeline
        piece={piece({ stage: "review", id: "p1" })}
        onUpdated={vi.fn()}
        interviewerPersonas={["ferriss", "skeptic"]}
      />,
    );
    const toggle = screen.getByRole("button", { name: /start another round of interviews/i });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("button", { name: "ferriss" })).not.toBeInTheDocument();

    fireEvent.click(toggle);

    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("button", { name: "ferriss" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /open round 1/i })).toBeInTheDocument();
  });

  it("lessons stage with nothing proposed yet renders the Propose lessons form, not Finish lessons", () => {
    vi.stubGlobal("fetch", vi.fn());
    render(<Pipeline piece={piece({ stage: "lessons", lessons: [] })} onUpdated={vi.fn()} />);
    expect(screen.getByLabelText("What was actually published")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Propose lessons" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /finish lessons/i })).not.toBeInTheDocument();
  });

  it("lessons stage with an unresolved proposal renders a link to resolve it, not Finish lessons or the propose form", () => {
    vi.stubGlobal("fetch", vi.fn());
    render(
      <Pipeline
        piece={piece({
          stage: "lessons",
          lessons: [{ id: "l1", observed_change: "x", generalizable_rule: "y", status: "proposed" }],
        })}
        onUpdated={vi.fn()}
      />,
    );
    const resolveLink = screen.getByRole("link", { name: /resolve 1 pending lesson/i });
    expect(resolveLink).toHaveAttribute("href", "/voice-kit");
    expect(screen.queryByRole("button", { name: /finish lessons/i })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("What was actually published")).not.toBeInTheDocument();
  });

  it("lessons stage with every proposal resolved renders Finish lessons, not the propose form or a resolve link", () => {
    vi.stubGlobal("fetch", vi.fn());
    render(
      <Pipeline
        piece={piece({
          stage: "lessons",
          lessons: [{ id: "l1", observed_change: "x", generalizable_rule: "y", status: "accepted" }],
        })}
        onUpdated={vi.fn()}
      />,
    );
    expect(screen.getByRole("button", { name: /finish lessons/i })).toBeInTheDocument();
    expect(screen.queryByLabelText("What was actually published")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /resolve/i })).not.toBeInTheDocument();
  });

  it("freshly finalized with no lessons ever proposed renders a real, clickable Authorize release button and no chip", () => {
    vi.stubGlobal("fetch", vi.fn());
    render(<Pipeline piece={piece({ stage: "finalized", lessons: [] })} onUpdated={vi.fn()} />);
    expect(screen.getByRole("button", { name: /authorize release/i })).toBeInTheDocument();
    expect(screen.queryByText(/awaiting accept\/reject/i)).not.toBeInTheDocument();
  });

  it("finalized with pending lessons keeps Publish primary but shows an equal-weight chip naming the pending count (decision A)", () => {
    vi.stubGlobal("fetch", vi.fn());
    render(
      <Pipeline
        piece={piece({
          stage: "finalized",
          lessons: [
            { id: "l1", observed_change: "x", generalizable_rule: "y", status: "proposed" },
            { id: "l2", observed_change: "x", generalizable_rule: "y", status: "proposed" },
          ],
        })}
        onUpdated={vi.fn()}
      />,
    );
    expect(screen.getByRole("button", { name: /authorize release/i })).toBeInTheDocument();
    expect(screen.getByText("2 lessons awaiting accept/reject")).toBeInTheDocument();
  });

  it("folds an open failure into the block itself (decision B) — no separate banner needed alongside it", () => {
    vi.stubGlobal("fetch", vi.fn());
    render(
      <Pipeline
        piece={piece({
          stage: "interviewing",
          failures: [
            {
              type: "draft",
              code: "ceiling-exceeded",
              message: "the model declined — no material on the stated purpose",
              triggered_by: "you@company",
              retryable: false,
              cost: 0.12,
            },
          ],
        })}
        onUpdated={vi.fn()}
      />,
    );
    expect(screen.getByText(/warns, doesn.t block/i)).toBeInTheDocument();
    expect(screen.getByText(/no material on the stated purpose/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
    // The current rail node reflects the failure, not a plain "interviewing" default.
    const current = screen.getByRole("listitem", { current: "step" });
    expect(current).toHaveTextContent("Interviewing");
  });

  it("dims the whole block when the piece is archived (decision D) — every control stays actionable underneath", () => {
    vi.stubGlobal("fetch", vi.fn());
    render(<Pipeline piece={piece({ archived_at: "2026-01-01T00:00:00.000Z" })} onUpdated={vi.fn()} />);
    const heading = screen.getByText("Pipeline");
    expect(heading.closest(".opacity-60")).toBeTruthy();
    // Still fully actionable — dimming is purely visual.
    expect(screen.getByRole("button", { name: /enough input → draft/i })).toBeEnabled();
  });

  it("does not dim when the piece is not archived", () => {
    vi.stubGlobal("fetch", vi.fn());
    render(<Pipeline piece={piece()} onUpdated={vi.fn()} />);
    const heading = screen.getByText("Pipeline");
    expect(heading.closest(".opacity-60")).toBeFalsy();
  });

  it("draws the review loop as a bracket with an escalating round chip, not a straight line — round 1 reads plain, round 3 reads as looping", () => {
    vi.stubGlobal("fetch", vi.fn());
    const { rerender } = render(
      <Pipeline
        piece={piece({
          stage: "review",
          review_round: {
            round_number: 1,
            minted_from_revision: "rev1",
            status: "open",
            share_mode: "internal",
            doc_url: null,
            opened_at: null,
            routing_log: [],
          },
        })}
        onUpdated={vi.fn()}
      />,
    );
    expect(screen.getByText(/round 1/i)).toBeInTheDocument();
    expect(screen.queryByText(/loop \d×/i)).not.toBeInTheDocument();

    rerender(
      <Pipeline
        piece={piece({
          stage: "incorporating",
          review_round: {
            round_number: 3,
            minted_from_revision: "rev3",
            status: "closed",
            share_mode: "internal",
            doc_url: null,
            opened_at: null,
            routing_log: [],
          },
        })}
        onUpdated={vi.fn()}
      />,
    );
    expect(screen.getByText(/round 3/i)).toBeInTheDocument();
    expect(screen.getByText(/loop 2×/i)).toBeInTheDocument();
  });

  it("keeps the paused chip off-rail — no cluster stage is marked current while paused", () => {
    vi.stubGlobal("fetch", vi.fn());
    render(<Pipeline piece={piece({ stage: "paused" })} onUpdated={vi.fn()} />);
    expect(screen.queryByRole("listitem", { current: "step" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^resume$/i })).toBeInTheDocument();
  });

  it("collapses the full stage → action reference table by default, expands on toggle, without touching the rail or the CTA", () => {
    vi.stubGlobal("fetch", vi.fn());
    render(<Pipeline piece={piece()} onUpdated={vi.fn()} />);
    expect(screen.queryByText(/“Enough input” → draft/i)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /show more details/i }));

    expect(screen.getByText(/“Enough input” → draft/i)).toBeInTheDocument();
    // The rail and the primary CTA button are unaffected — still visible throughout.
    expect(screen.getByRole("button", { name: /enough input → draft/i })).toBeInTheDocument();
  });
});
