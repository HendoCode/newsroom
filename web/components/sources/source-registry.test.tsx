import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SourceRegistry } from "@/components/sources/source-registry";
import type { Source, SourceListResponse } from "@/lib/sources/types";

// SourceRegistry calls `router.refresh()` after every mutation to invalidate the client-side
// Router Cache (cmw-source-registry-ux item 1) — no real Next.js router is mounted under plain
// Testing Library render(), so this seam needs a stub.
const routerRefresh = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: routerRefresh }),
}));

// jsdom has no real layout engine, so scrollIntoView isn't implemented at all.
Element.prototype.scrollIntoView = vi.fn();

const GDRIVE: Source = {
  id: "src-gdrive",
  display_name: "Call & webinar transcripts",
  kind: "gdrive",
  classification: "scraped-periodically",
  enabled: true,
  lookback_default_days: 7,
  config: { folder_ids: ["a"] },
  owner: "owner@example.com",
  last_refreshed: "2026-07-30T10:00:00.000Z",
};

const LINKEDIN: Source = {
  id: "src-linkedin",
  display_name: "LinkedIn / X clips",
  kind: "linkedin-x-clip",
  classification: "read-as-needed",
  enabled: true,
  lookback_default_days: 7,
  config: {},
  owner: null,
  last_refreshed: null,
};

const INITIAL: SourceListResponse = { source: "seed", items: [GDRIVE, LINKEDIN] };

afterEach(() => {
  vi.unstubAllGlobals();
  routerRefresh.mockClear();
});

describe("SourceRegistry", () => {
  it("toggling a row's switch PATCHes /api/sources/:id with the flipped enabled value", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ ...GDRIVE, enabled: false }),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<SourceRegistry initial={INITIAL} />);

    fireEvent.click(screen.getByRole("switch", { name: /disable call & webinar transcripts/i }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const call = fetchMock.mock.calls[0];
    if (!call) throw new Error("fetch was not called");
    const [url, options] = call;
    expect(url).toBe("/api/sources/src-gdrive");
    expect(options.method).toBe("PATCH");
    expect(JSON.parse(options.body)).toEqual({ enabled: false });
  });

  it("Refresh sources now posts the lookback window to /api/connectors/refresh and reports the outcome", async () => {
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url === "/api/connectors/refresh") {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            refreshed: [{ source_id: "src-gdrive", kind: "gdrive", ingested: 3, skipped: 1, error: null }],
          }),
        });
      }
      if (url === "/api/sources") {
        return Promise.resolve({ ok: true, json: async () => INITIAL });
      }
      throw new Error(`unexpected fetch ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<SourceRegistry initial={INITIAL} />);
    fireEvent.click(screen.getByRole("button", { name: /refresh sources now/i }));

    await screen.findByText(/refreshed 1 source — 3 new items/i);

    const refreshCall = fetchMock.mock.calls[0];
    if (!refreshCall) throw new Error("fetch was not called");
    const [refreshUrl, refreshOptions] = refreshCall;
    expect(refreshUrl).toBe("/api/connectors/refresh");
    expect(JSON.parse(refreshOptions.body)).toEqual({ lookback_days: 7 });
  });

  it("Edit populates the form with the row's values and offers Retire; + Add source resets it", () => {
    render(<SourceRegistry initial={INITIAL} />);

    const gdriveRow = screen.getByText("Call & webinar transcripts").closest("tr") as HTMLElement;
    fireEvent.click(within(gdriveRow).getByRole("button", { name: "Edit" }));

    expect(screen.getByLabelText("Display name")).toHaveValue("Call & webinar transcripts");
    expect(screen.getByRole("button", { name: "Retire source" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "+ Add source" }));

    expect(screen.getByLabelText("Display name")).toHaveValue("");
    expect(screen.queryByRole("button", { name: "Retire source" })).not.toBeInTheDocument();
  });

  it("+ Add source clears a blank-form draft even though the target was already \"new\" (item 3)", () => {
    // Regression for the "seems to do nothing" report: clicking Add while the form is already
    // showing "add" is a same-value setState with no target to change — only the resetKey bump
    // makes this visibly reset an in-progress, unsaved draft.
    render(<SourceRegistry initial={INITIAL} />);

    fireEvent.change(screen.getByLabelText("Display name"), { target: { value: "unsaved draft" } });
    expect(screen.getByLabelText("Display name")).toHaveValue("unsaved draft");

    fireEvent.click(screen.getByRole("button", { name: "+ Add source" }));

    expect(screen.getByLabelText("Display name")).toHaveValue("");
  });

  it("saving a new source confirms success, resets the form, and refreshes the router cache (item 2)", async () => {
    const created: Source = {
      id: "src-new",
      display_name: "O'Reilly Radar",
      kind: "web-rss",
      classification: "scraped-periodically",
      enabled: true,
      lookback_default_days: 7,
      config: { feed_urls: ["https://example.com/feed.xml"] },
      owner: "hendo@example.com",
      last_refreshed: null,
    };
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => created });
    vi.stubGlobal("fetch", fetchMock);

    render(<SourceRegistry initial={INITIAL} />);

    fireEvent.change(screen.getByLabelText("Display name"), { target: { value: "O'Reilly Radar" } });
    fireEvent.click(screen.getByRole("button", { name: "Save source" }));

    await screen.findByText(/added "o'reilly radar" to your sources/i);

    // The form reset even though it stayed on "new" the whole time — the bug this regresses.
    expect(screen.getByLabelText("Display name")).toHaveValue("");
    // The new row landed in the table.
    expect(screen.getByText("O'Reilly Radar")).toBeInTheDocument();
    // The client-side Router Cache is invalidated so a later browser-back won't serve a stale
    // pre-save snapshot of this route (item 1's shared root cause).
    expect(routerRefresh).toHaveBeenCalled();
  });

  describe("the add-source and clip-in panels are mutually exclusive (cmw-list-density-and-source-forms)", () => {
    it("shows only the add-source form by default, never the clip-in form alongside it", () => {
      render(<SourceRegistry initial={INITIAL} />);

      expect(screen.getByLabelText("Display name")).toBeInTheDocument();
      expect(screen.queryByLabelText("Paste text or URL")).not.toBeInTheDocument();
    });

    it("'Clip in a LinkedIn/X post' swaps to the clip-in form and hides the add-source form", () => {
      render(<SourceRegistry initial={INITIAL} />);

      fireEvent.click(screen.getByRole("button", { name: "Clip in a LinkedIn/X post" }));

      expect(screen.getByLabelText("Paste text or URL")).toBeInTheDocument();
      expect(screen.queryByLabelText("Display name")).not.toBeInTheDocument();

      fireEvent.click(screen.getByRole("button", { name: "+ Add source" }));

      expect(screen.getByLabelText("Display name")).toBeInTheDocument();
      expect(screen.queryByLabelText("Paste text or URL")).not.toBeInTheDocument();
    });

    it("clicking a row's Edit switches back to the add-source panel (in case the clip-in panel was showing)", () => {
      render(<SourceRegistry initial={INITIAL} />);
      fireEvent.click(screen.getByRole("button", { name: "Clip in a LinkedIn/X post" }));
      expect(screen.getByLabelText("Paste text or URL")).toBeInTheDocument();

      const gdriveRow = screen.getByText("Call & webinar transcripts").closest("tr") as HTMLElement;
      fireEvent.click(within(gdriveRow).getByRole("button", { name: "Edit" }));

      expect(screen.getByLabelText("Display name")).toHaveValue("Call & webinar transcripts");
      expect(screen.queryByLabelText("Paste text or URL")).not.toBeInTheDocument();
    });

    it("clicking Edit scrolls the form into view (cmw-source-edit-button-scroll)", () => {
      const scrollSpy = vi.mocked(Element.prototype.scrollIntoView);
      scrollSpy.mockClear();
      render(<SourceRegistry initial={INITIAL} />);

      const gdriveRow = screen.getByText("Call & webinar transcripts").closest("tr") as HTMLElement;
      fireEvent.click(within(gdriveRow).getByRole("button", { name: "Edit" }));

      expect(scrollSpy).toHaveBeenCalled();
    });

    it("the clip-in panel's empty state offers a shortcut that opens the add-source form preset to the clip-in kind", () => {
      // No linkedin-x-clip source in this list, unlike INITIAL.
      const noClip: SourceListResponse = { source: "seed", items: [GDRIVE] };
      render(<SourceRegistry initial={noClip} />);

      fireEvent.click(screen.getByRole("button", { name: "Clip in a LinkedIn/X post" }));
      fireEvent.click(screen.getByRole("button", { name: "Set up a clip-in source" }));

      expect(screen.getByLabelText("Display name")).toBeInTheDocument();
      expect(screen.getByLabelText("Kind")).toHaveValue("linkedin-x-clip");
    });
  });
});
