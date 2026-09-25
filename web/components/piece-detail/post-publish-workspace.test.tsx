import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { isPostPublish, PostPublishWorkspace } from "@/components/piece-detail/post-publish-workspace";
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
    published_html_url: "https://bucket.s3.amazonaws.com/published/p1/1/branded.html",
    published_pdf_url: null,
    published_doc: null,
    published_at: null,
    ...overrides,
  };
}

describe("isPostPublish", () => {
  it("is true for the terminal published stage or any release > 0", () => {
    expect(isPostPublish({ stage: "published", published_release: 1 })).toBe(true);
    expect(isPostPublish({ stage: "published", published_release: 0 })).toBe(true);
    expect(isPostPublish({ stage: "finalized", published_release: 1 })).toBe(true);
    expect(isPostPublish({ stage: "review", published_release: 0 })).toBe(false);
  });
});

describe("PostPublishWorkspace", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, json: async () => [] }),
    );
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("defaults to the Derivatives tab so publish is not the last thing on screen", () => {
    render(<PostPublishWorkspace piece={piece()} />);
    expect(screen.getByRole("tab", { name: "Derivatives" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Outputs" })).toHaveAttribute("aria-selected", "false");
    expect(screen.getByText(/publish is not the last beat/i)).toBeInTheDocument();
    expect(screen.queryByText(/branded html \(s3\)/i)).not.toBeInTheDocument();
  });

  it("the Outputs tab still shows the durable public links", () => {
    render(<PostPublishWorkspace piece={piece()} />);
    fireEvent.click(screen.getByRole("tab", { name: "Outputs" }));
    expect(screen.getByRole("tab", { name: "Outputs" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText(/branded html \(s3\)/i)).toBeInTheDocument();
    expect(screen.queryByText(/publish is not the last beat/i)).not.toBeInTheDocument();
  });
});
