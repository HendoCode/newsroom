import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { SpikesTable } from "@/components/spikes/spikes-table";
import type { Spike } from "@/lib/spikes/types";

function spike(overrides: Partial<Spike> = {}): Spike {
  return {
    id: "spike-1",
    headline: "You're auditing the wrong line item",
    status: "proposed",
    convergence_score: 0.64,
    creator: "demo-mira@example.com",
    origin: { kind: "narrative", ref: "narrative-1" },
    source_ids: [],
    customer_partner: null,
    outcome_metric: null,
    rank_rationale: null,
    convergence_note: null,
    intent: null,
    piece_id: null,
    updated_at: null,
    ...overrides,
  };
}

describe("SpikesTable — Pick & assign carries the caller's Voice forward (item 7)", () => {
  it("appends ?voice= to Pick & assign when a voiceHint is given", () => {
    render(
      <SpikesTable spikes={[spike()]} selectedId={null} onSelect={vi.fn()} voiceHint="demo-mira" />,
    );
    expect(screen.getByRole("link", { name: "Pick & assign" })).toHaveAttribute(
      "href",
      "/spikes/spike-1?voice=demo-mira",
    );
  });

  it("omits the query param entirely when there is no voiceHint (e.g. the plain Vault browser)", () => {
    render(<SpikesTable spikes={[spike()]} selectedId={null} onSelect={vi.fn()} />);
    expect(screen.getByRole("link", { name: "Pick & assign" })).toHaveAttribute(
      "href",
      "/spikes/spike-1",
    );
  });

  it("links an already-picked spike straight to its piece instead, regardless of voiceHint", () => {
    render(
      <SpikesTable
        spikes={[spike({ status: "picked", piece_id: "piece-1" })]}
        selectedId={null}
        onSelect={vi.fn()}
        voiceHint="demo-mira"
      />,
    );
    expect(screen.getByRole("link", { name: "Open piece" })).toHaveAttribute("href", "/pieces/piece-1");
  });
});
