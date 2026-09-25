import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FinalizeView } from "@/components/finalize/finalize-view";
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
    latest_revision: "rev-7",
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

describe("FinalizeView — distinct from Reviews done", () => {
  it("never renders a 'Reviews done' control on this screen", () => {
    vi.stubGlobal("fetch", vi.fn());
    render(<FinalizeView initial={piece()} />);
    expect(screen.queryByRole("button", { name: /reviews done/i })).not.toBeInTheDocument();
  });

  it("the Then card names Derivatives as the next beat, not 'distribution is out of v1'", () => {
    vi.stubGlobal("fetch", vi.fn());
    render(<FinalizeView initial={piece()} />);
    expect(screen.getByText(/derivatives tab/i)).toBeInTheDocument();
    expect(screen.getByText(/publish is not the last step/i)).toBeInTheDocument();
    expect(screen.queryByText(/distribution is out of v1/i)).not.toBeInTheDocument();
  });

  it("defaults every format to selected and posts formats: null (the step's own default)", async () => {
    const refreshed = piece({
      stage: "finalized",
      final_doc: { doc_id: "d1", url: "https://docs.google.com/x", share_mode: "internal" },
      final_template_version: "demo-dana/v3",
      final_rendered_at: "2026-07-30T12:00:00.000Z",
    });
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/api/pieces/p1/finalize") {
        expect(init?.method).toBe("POST");
        expect(JSON.parse(String(init?.body))).toEqual({ formats: null });
        return new Response(null, { status: 200 });
      }
      if (url === "/api/pieces/p1") {
        return new Response(JSON.stringify(refreshed), { status: 200 });
      }
      throw new Error(`unexpected fetch ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<FinalizeView initial={piece()} />);
    fireEvent.click(screen.getByRole("button", { name: /finalize & render outputs/i }));

    await waitFor(() => expect(screen.getByText(/last rendered/i)).toBeInTheDocument());
    expect(screen.getAllByText("demo-dana/v3").length).toBeGreaterThan(0);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    // The Doc of record link is real and clickable once the piece carries a final_doc.
    expect(screen.getAllByRole("link", { name: /open ↗/i })[0]).toHaveAttribute(
      "href",
      "https://docs.google.com/x",
    );
  });

  it("narrows the request when a format is deselected", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/api/pieces/p1/finalize") {
        expect(JSON.parse(String(init?.body))).toEqual({ formats: ["html", "pdf"] });
        return new Response(null, { status: 200 });
      }
      if (url === "/api/pieces/p1") {
        return new Response(JSON.stringify(piece({ stage: "finalized" })), { status: 200 });
      }
      throw new Error(`unexpected fetch ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<FinalizeView initial={piece()} />);
    fireEvent.click(screen.getByRole("checkbox", { name: /^clean google doc/i }));
    fireEvent.click(screen.getByRole("button", { name: /finalize & render outputs/i }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  });

  it("shows an inline error and does not crash when the finalize trigger is rejected", async () => {
    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify({ error: "no batch step registered for finalize" }), { status: 501 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<FinalizeView initial={piece()} />);
    fireEvent.click(screen.getByRole("button", { name: /finalize & render outputs/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/no batch step registered/i);
  });

  it("disables the Finalize action and explains why when the piece isn't in review", () => {
    vi.stubGlobal("fetch", vi.fn());
    render(<FinalizeView initial={piece({ stage: "finalized" })} />);
    expect(screen.getByRole("button", { name: /finalize & render outputs/i })).toBeDisabled();
    expect(screen.getByText(/only available from/i)).toBeInTheDocument();
  });

  it("deselecting every format disables Finalize with an inline hint (not a silent no-op)", () => {
    vi.stubGlobal("fetch", vi.fn());
    render(<FinalizeView initial={piece()} />);
    for (const checkbox of screen.getAllByRole("checkbox")) {
      fireEvent.click(checkbox);
    }
    expect(screen.getByRole("button", { name: /finalize & render outputs/i })).toBeDisabled();
    expect(screen.getByText(/select at least one output format/i)).toBeInTheDocument();
  });
});
