import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { SourcesTable } from "@/components/sources/sources-table";
import type { Source } from "@/lib/sources/types";

const NOW = new Date("2026-07-30T12:00:00.000Z");

const SOURCES: Source[] = [
  {
    id: "src-gdrive",
    display_name: "Call & webinar transcripts",
    kind: "gdrive",
    classification: "scraped-periodically",
    enabled: true,
    lookback_default_days: 7,
    config: { folder_ids: ["a", "b", "c"] },
    owner: "owner@example.com",
    last_refreshed: "2026-07-30T10:00:00.000Z",
  },
  {
    id: "src-linkedin",
    display_name: "LinkedIn / X clips",
    kind: "linkedin-x-clip",
    classification: "read-as-needed",
    enabled: false,
    lookback_default_days: 7,
    config: {},
    owner: null,
    last_refreshed: null,
  },
];

describe("SourcesTable", () => {
  it("collapses each row to name/kind/classification by default, with config/credential/last-refreshed behind the expand toggle", () => {
    render(
      <SourcesTable sources={SOURCES} now={NOW} onToggle={vi.fn()} onEdit={vi.fn()} togglingId={null} />,
    );

    expect(screen.getByText("Call & webinar transcripts")).toBeInTheDocument();
    expect(screen.getByText("owner: owner@example.com")).toBeInTheDocument();
    expect(screen.getByText("LinkedIn / X clips")).toBeInTheDocument();
    expect(screen.getByText("read-as-needed")).toBeInTheDocument();

    // Collapsed by default (row density at scale, cmw-list-density-and-source-forms) — the detail
    // fields aren't in the document at all until expanded.
    expect(screen.queryByText("2h ago")).not.toBeInTheDocument();
    expect(screen.queryByText("3 folder IDs")).not.toBeInTheDocument();
    expect(screen.queryByText("manual paste (below)")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /show more details.*call & webinar transcripts/i }));
    expect(screen.getByText("2h ago")).toBeInTheDocument();
    expect(screen.getByText("3 folder IDs")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /show more details.*linkedin \/ x clips/i }));
    expect(screen.getByText("manual paste (below)")).toBeInTheDocument();

    // The deferred Gmail row is always present and clearly labeled, never a real registry entry.
    expect(screen.getByText("Gmail")).toBeInTheDocument();
    expect(screen.getByText("deferred")).toBeInTheDocument();
    expect(screen.getByText("opt-in, later (§9)")).toBeInTheDocument();
  });

  it("toggling a source's switch calls onToggle with the flipped value", () => {
    const onToggle = vi.fn();
    render(
      <SourcesTable sources={SOURCES} now={NOW} onToggle={onToggle} onEdit={vi.fn()} togglingId={null} />,
    );

    fireEvent.click(screen.getByRole("switch", { name: /disable call & webinar transcripts/i }));
    expect(onToggle).toHaveBeenCalledWith(SOURCES[0], false);

    fireEvent.click(screen.getByRole("switch", { name: /enable linkedin \/ x clips/i }));
    expect(onToggle).toHaveBeenCalledWith(SOURCES[1], true);
  });

  it("the deferred Gmail row's toggle is disabled and has no edit action", () => {
    render(
      <SourcesTable sources={SOURCES} now={NOW} onToggle={vi.fn()} onEdit={vi.fn()} togglingId={null} />,
    );
    const gmailSwitch = screen.getByRole("switch", { name: /gmail/i });
    expect(gmailSwitch).toBeDisabled();

    const gmailRow = screen.getByText("Gmail").closest("tr");
    expect(gmailRow).not.toBeNull();
    expect(within(gmailRow as HTMLElement).queryByRole("button", { name: "Edit" })).toBeNull();
  });

  it("clicking Edit on a row calls onEdit with that source", () => {
    const onEdit = vi.fn();
    render(
      <SourcesTable sources={SOURCES} now={NOW} onToggle={vi.fn()} onEdit={onEdit} togglingId={null} />,
    );

    const gdriveRow = screen.getByText("Call & webinar transcripts").closest("tr") as HTMLElement;
    fireEvent.click(within(gdriveRow).getByRole("button", { name: "Edit" }));
    expect(onEdit).toHaveBeenCalledWith(SOURCES[0]);
  });

  it("shows a source's refresh error inline, and only for the source it belongs to (item 2)", () => {
    render(
      <SourcesTable
        sources={SOURCES}
        now={NOW}
        onToggle={vi.fn()}
        onEdit={vi.fn()}
        togglingId={null}
        refreshErrors={{ "src-gdrive": "Google Drive OAuth not configured" }}
      />,
    );

    expect(screen.getByRole("alert")).toHaveTextContent("Google Drive OAuth not configured");
    // The aggregate refresh summary used to be the only trace of this — nothing named the source.
    expect(screen.getByRole("alert")).toHaveTextContent("Call & webinar transcripts");
  });

  it("shows no error banner when nothing failed on the last refresh", () => {
    render(
      <SourcesTable sources={SOURCES} now={NOW} onToggle={vi.fn()} onEdit={vi.fn()} togglingId={null} />,
    );
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("disables the toggle for the row currently being saved", () => {
    render(
      <SourcesTable
        sources={SOURCES}
        now={NOW}
        onToggle={vi.fn()}
        onEdit={vi.fn()}
        togglingId="src-gdrive"
      />,
    );
    expect(screen.getByRole("switch", { name: /disable call & webinar transcripts/i })).toBeDisabled();
    expect(screen.getByRole("switch", { name: /enable linkedin \/ x clips/i })).not.toBeDisabled();
  });
});
