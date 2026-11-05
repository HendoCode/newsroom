import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ProposeLessonsForm } from "@/components/piece-detail/propose-lessons-form";
import type { PieceDetail } from "@/lib/pieces/types";

function piece(overrides: Partial<PieceDetail> = {}): PieceDetail {
  return {
    id: "p1",
    slug: "token-vs-storage",
    title: "token-vs-storage",
    voice: "demo-mira",
    stage: "lessons",
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

describe("ProposeLessonsForm", () => {
  it("disables submit until text is pasted", () => {
    vi.stubGlobal("fetch", vi.fn());
    render(<ProposeLessonsForm pieceId="p1" onUpdated={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Propose lessons" })).toBeDisabled();
    fireEvent.change(screen.getByLabelText("What was actually published"), {
      target: { value: "the actual published text" },
    });
    expect(screen.getByRole("button", { name: "Propose lessons" })).not.toBeDisabled();
  });

  it("posts published_content, refetches the piece, and reports the count of proposed lessons", async () => {
    const refreshed = piece({
      lessons: [{ id: "l1", observed_change: "x", generalizable_rule: "y", status: "proposed" }],
    });
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/api/pieces/p1/lessons/propose") {
        expect(init?.method).toBe("POST");
        expect(JSON.parse(String(init?.body))).toEqual({
          published_content: "the actual published text",
        });
        return new Response(
          JSON.stringify({
            proposed: [{ id: "l1", voice: "demo-mira", source_piece_id: "p1", observed_change: "x", generalizable_rule: "y", status: "proposed" }],
          }),
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
    render(<ProposeLessonsForm pieceId="p1" onUpdated={onUpdated} />);

    fireEvent.change(screen.getByLabelText("What was actually published"), {
      target: { value: "the actual published text" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Propose lessons" }));

    await waitFor(() => expect(onUpdated).toHaveBeenCalledWith(refreshed));
    expect(fetchMock).toHaveBeenCalledTimes(2);
    await screen.findByText(/1 lesson proposed/i);
    // The textarea clears after a successful propose call.
    expect(screen.getByLabelText("What was actually published")).toHaveValue("");
  });

  it("reports when the diff found nothing worth proposing", async () => {
    const refreshed = piece();
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/pieces/p1/lessons/propose") {
        return new Response(JSON.stringify({ proposed: [] }), { status: 200 });
      }
      if (url === "/api/pieces/p1") {
        return new Response(JSON.stringify(refreshed), { status: 200 });
      }
      throw new Error(`unexpected fetch ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<ProposeLessonsForm pieceId="p1" onUpdated={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("What was actually published"), {
      target: { value: "identical to the final draft" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Propose lessons" }));

    await screen.findByText(/no meaningful difference found/i);
  });

  it("surfaces the error message and keeps the pasted text when the propose call fails", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      json: async () => ({ error: "piece \"p1\" is not in the lessons stage" }),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<ProposeLessonsForm pieceId="p1" onUpdated={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("What was actually published"), {
      target: { value: "some published text" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Propose lessons" }));

    await screen.findByText('piece "p1" is not in the lessons stage');
    expect(screen.getByLabelText("What was actually published")).toHaveValue("some published text");
  });
});
