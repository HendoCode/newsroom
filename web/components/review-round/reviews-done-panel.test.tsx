import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ReviewsDonePanel } from "@/components/review-round/reviews-done-panel";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ReviewsDonePanel — no path to a blind fire", () => {
  it("disables Confirm until a preview has loaded", () => {
    vi.stubGlobal("fetch", vi.fn());
    render(<ReviewsDonePanel pieceId="p1" disabled={false} onConfirmed={vi.fn()} />);
    expect(screen.getByRole("button", { name: /confirm — reviews done/i })).toBeDisabled();
  });

  it("loads the preview (counts + samples), then enables Confirm, which fires the reviews-done trigger", async () => {
    const onConfirmed = vi.fn();
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/api/pieces/p1/review/preview") {
        return new Response(
          JSON.stringify({
            round_number: 1,
            comment_count: 2,
            edit_count: 1,
            no_changes: false,
            diff_degraded: false,
            samples: ["please tighten this claim", "typo in paragraph 2"],
          }),
          { status: 200 },
        );
      }
      if (url === "/api/pieces/p1/trigger") {
        expect(JSON.parse(String(init?.body))).toEqual({ trigger: "reviews-done" });
        return new Response(null, { status: 200 });
      }
      throw new Error(`unexpected fetch ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<ReviewsDonePanel pieceId="p1" disabled={false} onConfirmed={onConfirmed} />);
    fireEvent.click(screen.getByRole("button", { name: /preview what will fold in/i }));

    expect(await screen.findByText(/2 comments · 1 inline edit detected/i)).toBeInTheDocument();
    expect(screen.getByText("please tighten this claim")).toBeInTheDocument();

    const confirm = screen.getByRole("button", { name: /confirm — reviews done/i });
    expect(confirm).not.toBeDisabled();
    fireEvent.click(confirm);

    await waitFor(() => expect(onConfirmed).toHaveBeenCalledTimes(1));
  });

  it("shows a friendly message (not a raw 404) when there is no open round to preview", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ error: "no piece" }), { status: 404 })),
    );
    render(<ReviewsDonePanel pieceId="p1" disabled={false} onConfirmed={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: /preview what will fold in/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/mint a doc first/i);
    expect(screen.getByRole("button", { name: /confirm — reviews done/i })).toBeDisabled();
  });

  it("disables every control outside the review stage", () => {
    vi.stubGlobal("fetch", vi.fn());
    render(<ReviewsDonePanel pieceId="p1" disabled onConfirmed={vi.fn()} />);
    expect(screen.getByRole("button", { name: /preview what will fold in/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /confirm — reviews done/i })).toBeDisabled();
  });
});
