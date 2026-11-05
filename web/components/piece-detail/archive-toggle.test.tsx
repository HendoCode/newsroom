import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ArchiveToggle } from "@/components/piece-detail/archive-toggle";
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
    archived_at: null,
    ...overrides,
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ArchiveToggle — status-orthogonal, never gated on stage", () => {
  it("posts /archive, then refetches and reports the refreshed (archived) piece", async () => {
    const refreshed = piece({ archived_at: "2026-08-10T00:00:00Z" });
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/api/pieces/p1/archive") {
        expect(init?.method).toBe("POST");
        return new Response(JSON.stringify({ id: "p1", slug: "x", archived_at: "2026-08-10T00:00:00Z" }), {
          status: 200,
        });
      }
      if (url === "/api/pieces/p1") {
        return new Response(JSON.stringify(refreshed), { status: 200 });
      }
      throw new Error(`unexpected fetch ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    const onUpdated = vi.fn();
    render(<ArchiveToggle piece={piece()} onUpdated={onUpdated} />);

    fireEvent.click(screen.getByRole("button", { name: /^archive$/i }));

    await waitFor(() => expect(onUpdated).toHaveBeenCalledWith(refreshed));
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("renders Unarchive and posts /unarchive once the piece is already archived", async () => {
    const refreshed = piece({ archived_at: null });
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/pieces/p1/unarchive") {
        return new Response(JSON.stringify({ id: "p1", slug: "x", archived_at: null }), { status: 200 });
      }
      if (url === "/api/pieces/p1") {
        return new Response(JSON.stringify(refreshed), { status: 200 });
      }
      throw new Error(`unexpected fetch ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    const onUpdated = vi.fn();
    render(<ArchiveToggle piece={piece({ archived_at: "2026-08-09T00:00:00Z" })} onUpdated={onUpdated} />);

    const button = screen.getByRole("button", { name: /unarchive/i });
    fireEvent.click(button);

    await waitFor(() => expect(onUpdated).toHaveBeenCalledWith(refreshed));
  });

  it("shows an inline error and does not call onUpdated when the request fails", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ error: "boom" }), { status: 502 }));
    vi.stubGlobal("fetch", fetchMock);

    const onUpdated = vi.fn();
    render(<ArchiveToggle piece={piece()} onUpdated={onUpdated} />);

    fireEvent.click(screen.getByRole("button", { name: /^archive$/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/boom/i);
    expect(onUpdated).not.toHaveBeenCalled();
  });

  it("is available at every stage, including the terminal published stage", () => {
    vi.stubGlobal("fetch", vi.fn());
    render(<ArchiveToggle piece={piece({ stage: "published" })} onUpdated={vi.fn()} />);
    expect(screen.getByRole("button", { name: /^archive$/i })).toBeEnabled();
  });
});
