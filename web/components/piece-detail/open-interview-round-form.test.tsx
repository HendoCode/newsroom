import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { OpenInterviewRoundForm } from "@/components/piece-detail/open-interview-round-form";
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

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("OpenInterviewRoundForm", () => {
  it("opens the interview, routes to interviewing, refetches, and reports the refreshed piece", async () => {
    const refreshed = piece({ stage: "interviewing" });
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/api/pieces/p1/interviews") {
        expect(init?.method).toBe("POST");
        expect(JSON.parse(String(init?.body))).toEqual({
          interviewer_personas: ["ferriss"],
          assigned_expert: "expert@example.com",
          about: "follow-up on pricing",
          is_gap_interview: true,
        });
        return new Response(JSON.stringify({ id: "iv2", piece_id: "p1" }), { status: 200 });
      }
      if (url === "/api/pieces/p1/trigger") {
        expect(JSON.parse(String(init?.body))).toEqual({ trigger: "route-to-interview" });
        return new Response(null, { status: 200 });
      }
      if (url === "/api/pieces/p1") {
        return new Response(JSON.stringify(refreshed), { status: 200 });
      }
      throw new Error(`unexpected fetch ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    const onUpdated = vi.fn();
    render(
      <OpenInterviewRoundForm
        pieceId="p1"
        personas={["ferriss", "skeptic"]}
        roundNumber={2}
        onUpdated={onUpdated}
      />,
    );

    // Both "ferriss" and "skeptic" are pre-selected by defaultInterviewerSelection's known-persona
    // preference — deselect "skeptic" so the submitted body is exactly ["ferriss"].
    fireEvent.click(screen.getByRole("button", { name: "skeptic" }));
    fireEvent.change(screen.getByLabelText(/assigned expert/i), {
      target: { value: "expert@example.com" },
    });
    fireEvent.change(screen.getByLabelText(/what this round is about/i), {
      target: { value: "follow-up on pricing" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Open round 2" }));

    await waitFor(() => expect(onUpdated).toHaveBeenCalledWith(refreshed));
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(screen.getByRole("link", { name: /open the interview/i })).toHaveAttribute(
      "href",
      "/interviews/iv2",
    );
    // The interview is real — the form itself must not still be showing (no resubmit control).
    expect(screen.queryByRole("button", { name: /open round/i })).not.toBeInTheDocument();
  });

  it("surfaces the open-interview failure and never fires route-to-interview", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/pieces/p1/interviews") {
        return new Response(JSON.stringify({ error: "unknown interviewer persona: nope" }), {
          status: 422,
        });
      }
      throw new Error(`unexpected fetch ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <OpenInterviewRoundForm pieceId="p1" personas={["ferriss"]} roundNumber={2} onUpdated={vi.fn()} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Open round 2" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/unknown interviewer persona/i);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("keeps the opened interview visible even when route-to-interview itself fails, and never re-shows the form", async () => {
    const refreshed = piece({ stage: "review" });
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/pieces/p1/interviews") {
        return new Response(JSON.stringify({ id: "iv2", piece_id: "p1" }), { status: 200 });
      }
      if (url === "/api/pieces/p1/trigger") {
        return new Response(
          JSON.stringify({ error: "route_to_interview is only legal from council/review, not drafting" }),
          { status: 409 },
        );
      }
      if (url === "/api/pieces/p1") {
        return new Response(JSON.stringify(refreshed), { status: 200 });
      }
      throw new Error(`unexpected fetch ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    const onUpdated = vi.fn();
    render(
      <OpenInterviewRoundForm pieceId="p1" personas={["ferriss"]} roundNumber={2} onUpdated={onUpdated} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Open round 2" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/could not be routed back to interviewing/i);
    expect(screen.getByRole("link", { name: /open the interview/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /open round/i })).not.toBeInTheDocument();
    await waitFor(() => expect(onUpdated).toHaveBeenCalledWith(refreshed));
  });

  it("disables submit until at least one persona is selected", () => {
    vi.stubGlobal("fetch", vi.fn());
    render(
      <OpenInterviewRoundForm pieceId="p1" personas={["nobody-preferred"]} roundNumber={1} onUpdated={vi.fn()} />,
    );
    // No known-preference persona in the roster → defaultInterviewerSelection falls back to the
    // first three available, so this one IS pre-selected; deselect it to hit the disabled state.
    fireEvent.click(screen.getByRole("button", { name: "nobody-preferred" }));
    expect(screen.getByRole("button", { name: "Open round 1" })).toBeDisabled();
  });
});
