import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { MintPanel } from "@/components/review-round/mint-panel";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("MintPanel", () => {
  it("mints internal by default, posting reviewer_emails: null when the textarea is empty", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      expect(String(input)).toBe("/api/pieces/p1/review/mint");
      expect(JSON.parse(String(init?.body))).toEqual({ share_mode: "internal", reviewer_emails: null });
      return new Response(
        JSON.stringify({ round_number: 1, doc_url: "https://docs.google.com/x", share_mode: "internal", warnings: [] }),
        { status: 200 },
      );
    });
    vi.stubGlobal("fetch", fetchMock);

    const onMinted = vi.fn();
    render(<MintPanel pieceId="p1" disabled={false} onMinted={onMinted} />);
    fireEvent.click(screen.getByRole("button", { name: /mint review doc/i }));

    await waitFor(() => expect(onMinted).toHaveBeenCalledTimes(1));
    expect(screen.getByText(/round 1 opened \(internal\)/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /open the doc/i })).toHaveAttribute(
      "href",
      "https://docs.google.com/x",
    );
  });

  it("shows the D11 clearance-check banner as soon as external is selected, before minting", () => {
    vi.stubGlobal("fetch", vi.fn());
    render(<MintPanel pieceId="p1" disabled={false} onMinted={vi.fn()} />);
    expect(screen.queryByText(/clearance check enforced/i)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("radio", { name: /external/i }));
    expect(screen.getByText(/clearance check enforced/i)).toBeInTheDocument();
  });

  it("parses comma/newline-separated reviewer emails and surfaces returned warnings", async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      expect(JSON.parse(String(init?.body))).toEqual({
        share_mode: "external",
        reviewer_emails: ["a@x.com", "b@x.com"],
      });
      return new Response(
        JSON.stringify({
          round_number: 3,
          doc_url: "https://docs.google.com/y",
          share_mode: "external",
          warnings: ["external share with 2 open GAP(s) — proceeding (warns, does not block, D11)"],
        }),
        { status: 200 },
      );
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<MintPanel pieceId="p1" disabled={false} onMinted={vi.fn()} />);
    fireEvent.click(screen.getByRole("radio", { name: /external/i }));
    fireEvent.change(screen.getByPlaceholderText(/reviewer1@company.com/i), {
      target: { value: "a@x.com,\nb@x.com" },
    });
    fireEvent.click(screen.getByRole("button", { name: /mint review doc/i }));

    expect(await screen.findByText(/proceeding/i)).toBeInTheDocument();
  });

  it("disables every control and explains why outside the review stage", () => {
    vi.stubGlobal("fetch", vi.fn());
    render(<MintPanel pieceId="p1" disabled onMinted={vi.fn()} />);
    expect(screen.getByRole("button", { name: /mint review doc/i })).toBeDisabled();
    expect(screen.getByText(/only legal in the/i)).toBeInTheDocument();
  });

  it("shows an inline error and does not call onMinted when the mint is rejected", async () => {
    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify({ error: "piece 'p1' is not in the review stage (stage=drafting)" }), {
        status: 409,
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const onMinted = vi.fn();
    render(<MintPanel pieceId="p1" disabled={false} onMinted={onMinted} />);
    fireEvent.click(screen.getByRole("button", { name: /mint review doc/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/not in the review stage/i);
    expect(onMinted).not.toHaveBeenCalled();
  });
});
