import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { NarrativeReveal } from "@/components/spikes/narrative-reveal";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("NarrativeReveal — the only way to see a spoken narrative again (item 6)", () => {
  it("fetches and shows the narrative's full seed_text on demand, not on mount", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        id: "narrative-1",
        author: "hendo@example.com",
        seed_text: "Enterprises keep betting everything on one region and one vendor.",
        intent: { audience: null, angle: null },
        oracle_run_id: "run-1",
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<NarrativeReveal narrativeId="narrative-1" />);
    expect(fetchMock).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: /view the narrative/i }));

    await screen.findByText(/enterprises keep betting everything/i);
    expect(fetchMock).toHaveBeenCalledWith("/api/narratives/narrative-1");

    // Toggling again hides it without re-fetching.
    fireEvent.click(screen.getByRole("button", { name: /hide/i }));
    expect(screen.queryByText(/enterprises keep betting everything/i)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /view the narrative/i }));
    await screen.findByText(/enterprises keep betting everything/i);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("surfaces a real error instead of failing silently", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      json: async () => ({ error: "no narrative 'narrative-1'" }),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<NarrativeReveal narrativeId="narrative-1" />);
    fireEvent.click(screen.getByRole("button", { name: /view the narrative/i }));

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/no narrative/i));
  });

  it("honors a caller-supplied subject for View/Hide copy (e.g. piece-detail's non-spike context)", () => {
    vi.stubGlobal("fetch", vi.fn());
    render(<NarrativeReveal narrativeId="narrative-1" subject="the narrative that started this piece" />);

    const toggle = screen.getByRole("button", { name: "View the narrative that started this piece" });
    fireEvent.click(toggle);
    expect(screen.getByRole("button", { name: "Hide the narrative that started this piece" })).toBeInTheDocument();
  });
});
