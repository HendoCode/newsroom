import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PublishedOutputs } from "@/components/piece-detail/published-outputs";
import type { PieceDetail } from "@/lib/pieces/types";

function piece(overrides: Partial<PieceDetail> = {}): PieceDetail {
  return {
    id: "p1",
    slug: "token-vs-storage",
    title: "token-vs-storage",
    voice: "demo-mira",
    stage: "published",
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
    published_release: 1,
    published_html_url: null,
    published_pdf_url: null,
    published_doc: null,
    published_at: null,
    ...overrides,
  };
}

describe("PublishedOutputs", () => {
  it("renders nothing before any publish", () => {
    const { container } = render(<PublishedOutputs piece={piece({ published_release: 0 })} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows S3 links and 'not produced' for the Drive copies when the Shared Drive wasn't configured", () => {
    render(
      <PublishedOutputs
        piece={piece({
          published_html_url: "https://bucket.s3.amazonaws.com/published/p1/1/branded.html",
          published_pdf_url: "https://bucket.s3.amazonaws.com/published/p1/1/branded.pdf",
        })}
      />,
    );

    expect(screen.getAllByRole("link", { name: /^open$/i, hidden: true }).length).toBe(2); // S3 HTML + PDF
    expect(screen.getAllByText(/not produced this release/i).length).toBe(3); // Doc + Drive HTML + Drive PDF
  });

  it("shows both S3 and Drive links once publish populated both destinations", () => {
    render(
      <PublishedOutputs
        piece={piece({
          published_html_url: "https://bucket.s3.amazonaws.com/published/p1/1/branded.html",
          published_pdf_url: "https://bucket.s3.amazonaws.com/published/p1/1/branded.pdf",
          published_doc: { doc_id: "d1", url: "https://docs.google.com/d1", share_mode: "external" },
          published_drive_html: { file_id: "h1", url: "https://drive.google.com/file/d/h1/view" },
          published_drive_pdf: { file_id: "p1", url: "https://drive.google.com/file/d/p1/view" },
        })}
      />,
    );

    const hrefs = screen.getAllByRole("link", { hidden: true }).map((l) => l.getAttribute("href"));
    expect(hrefs).toContain("https://bucket.s3.amazonaws.com/published/p1/1/branded.html");
    expect(hrefs).toContain("https://bucket.s3.amazonaws.com/published/p1/1/branded.pdf");
    expect(hrefs).toContain("https://docs.google.com/d1");
    expect(hrefs).toContain("https://drive.google.com/file/d/h1/view");
    expect(hrefs).toContain("https://drive.google.com/file/d/p1/view");
  });
});
