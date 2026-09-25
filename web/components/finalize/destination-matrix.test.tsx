import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { DestinationMatrix } from "@/components/finalize/destination-matrix";
import { DEFAULT_FINALIZE_FORMATS, type FinalizeFormat } from "@/lib/finalize/types";
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

function Wrapper({ initial }: { initial: PieceDetail }) {
  const [selected, setSelected] = useState<FinalizeFormat[]>([...DEFAULT_FINALIZE_FORMATS]);
  return (
    <DestinationMatrix
      piece={initial}
      selected={selected}
      onToggle={(format: FinalizeFormat) =>
        setSelected((prev: FinalizeFormat[]) =>
          prev.includes(format) ? prev.filter((f) => f !== format) : [...prev, format],
        )
      }
    />
  );
}

describe("DestinationMatrix", () => {
  it("shows no piece-folder link and every destination as not-yet-produced before finalize", () => {
    render(<Wrapper initial={piece()} />);

    expect(screen.queryByRole("link", { name: /open this piece.s drive folder/i })).not.toBeInTheDocument();
    expect(screen.getByText(/no drive folder yet/i)).toBeInTheDocument();
    expect(screen.getAllByText(/not yet produced/i).length).toBe(3); // Doc/HTML/PDF Drive cells
    expect(screen.getAllByText(/not published yet/i).length).toBe(2); // HTML/PDF S3 cells
    expect(screen.getByText(/n\/a — a doc is a drive object/i)).toBeInTheDocument();
  });

  it("links to the piece's Drive folder once one exists", () => {
    render(<Wrapper initial={piece({ drive_folder_url: "https://drive.google.com/drive/folders/f1" })} />);

    expect(screen.getByRole("link", { name: /open this piece.s drive folder/i })).toHaveAttribute(
      "href",
      "https://drive.google.com/drive/folders/f1",
    );
  });

  it("links each produced Drive artifact to its own file", () => {
    render(
      <Wrapper
        initial={piece({
          final_doc: { doc_id: "d1", url: "https://docs.google.com/d1", share_mode: "internal" },
          final_drive_html: { file_id: "h1", url: "https://drive.google.com/file/d/h1/view" },
          final_drive_pdf: { file_id: "p1", url: "https://drive.google.com/file/d/p1/view" },
        })}
      />,
    );

    const openLinks = screen.getAllByRole("link", { name: /^open ↗/i });
    const hrefs = openLinks.map((l) => l.getAttribute("href"));
    expect(hrefs).toContain("https://docs.google.com/d1");
    expect(hrefs).toContain("https://drive.google.com/file/d/h1/view");
    expect(hrefs).toContain("https://drive.google.com/file/d/p1/view");
  });

  it("links each published S3 artifact, independent of the Drive column", () => {
    render(
      <Wrapper
        initial={piece({
          published_html_url: "https://bucket.s3.amazonaws.com/published/p1/1/branded.html",
          published_pdf_url: "https://bucket.s3.amazonaws.com/published/p1/1/branded.pdf",
        })}
      />,
    );

    const openLinks = screen.getAllByRole("link", { name: /^open ↗/i });
    const hrefs = openLinks.map((l) => l.getAttribute("href"));
    expect(hrefs).toContain("https://bucket.s3.amazonaws.com/published/p1/1/branded.html");
    expect(hrefs).toContain("https://bucket.s3.amazonaws.com/published/p1/1/branded.pdf");
    // Still exactly two Drive cells say "not yet produced" (HTML/PDF) and the Doc's Drive cell too.
    expect(screen.getAllByText(/not yet produced/i).length).toBe(3);
  });

  it("toggling a checkbox calls back with that format, independent of destination links", () => {
    const onToggle = vi.fn();
    render(
      <DestinationMatrix piece={piece()} selected={[...DEFAULT_FINALIZE_FORMATS]} onToggle={onToggle} />,
    );

    fireEvent.click(screen.getByRole("checkbox", { name: /^clean google doc/i }));

    expect(onToggle).toHaveBeenCalledWith("doc");
  });

  it("disables every checkbox when disabled is set", () => {
    render(
      <DestinationMatrix piece={piece()} selected={[...DEFAULT_FINALIZE_FORMATS]} onToggle={vi.fn()} disabled />,
    );

    for (const checkbox of screen.getAllByRole("checkbox")) {
      expect(checkbox).toBeDisabled();
    }
  });
});
