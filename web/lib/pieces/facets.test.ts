import { describe, expect, it } from "vitest";

import {
  attentionState,
  executionState,
  facetSummaries,
  FACET_ORDER,
  learningState,
  type FacetKind,
} from "@/lib/pieces/facets";
import type { PieceDetail } from "@/lib/pieces/types";

function piece(overrides: Partial<PieceDetail> = {}): PieceDetail {
  return {
    id: "p1",
    slug: "token-vs-storage",
    title: "token-vs-storage",
    voice: "demo-mira",
    stage: "review",
    owner: null,
    assigned_experts: [],
    origin_spike_id: null,
    target: null,
    partners: [],
    open_gaps: 0,
    open_clearances: 0,
    latest_revision: "abc1234def",
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

function facet(overrides: Partial<PieceDetail>, kind: FacetKind) {
  const found = facetSummaries(piece(overrides)).find((s) => s.kind === kind);
  if (!found) throw new Error(`no facet ${kind}`);
  return found;
}

describe("facetSummaries", () => {
  it("emits all six facets in the canonical lifecycle order", () => {
    const summaries = facetSummaries(piece());
    expect(summaries.map((s) => s.kind)).toEqual(FACET_ORDER);
    expect(summaries.map((s) => s.kind)).toEqual([
      "stage",
      "execution",
      "review",
      "attention",
      "lineage",
      "learning",
    ]);
  });

  it("reads stage + round for a loop stage, plain stage elsewhere", () => {
    expect(
      facet({ stage: "council", review_round: { round_number: 2 } as never }, "stage").value,
    ).toContain("round 2");
    expect(facet({ stage: "interviewing" }, "stage").value).not.toContain("round");
  });

  it("reads the review facet off the latest council pass", () => {
    const none = facet({}, "review");
    expect(none.value).toBe("no council yet");
    expect(none.tone).toBe("neutral");

    const scored = facet(
      {
        council: {
          round_number: 1,
          iteration: 1,
          revision: "rev-1",
          aggregate: 8.5,
          cost: 0.1,
          stop_reason: null,
          stop_message: null,
          editor_scores: [],
        },
      },
      "review",
    );
    expect(scored.value).toBe("8.5 · r1");
    expect(scored.tone).toBe("success");
  });

  it("reads lineage off revision + origin + brain-synced provenance", () => {
    expect(facet({}, "lineage").value).toBe("rev abc1234");

    const full = facet({ origin_spike_id: "spike-1", brain_synced: true }, "lineage").value;
    expect(full).toContain("from spike");
    expect(full).toContain("brain draft");

    expect(facet({ latest_revision: null }, "lineage").value).toBe("no revision");
  });
});

describe("executionState", () => {
  it("is idle with no jobs in flight and no failures", () => {
    expect(executionState(piece()).status).toBe("idle");
  });

  it("reads the machine's running signal off the activity log's job lines", () => {
    const running = executionState(
      piece({ activity: [{ label: "draft job running", detail: null, at: null }] }),
    );
    expect(running.status).toBe("running");
    const queued = executionState(
      piece({ activity: [{ label: "council job queued", detail: null, at: null }] }),
    );
    expect(queued.status).toBe("running");
    // A completed job line is not a running signal.
    const done = executionState(
      piece({ activity: [{ label: "draft job ok", detail: null, at: null }] }),
    );
    expect(done.status).toBe("idle");
  });

  it("outranks a running job with an open failure (flag-not-rollback)", () => {
    const failed = executionState(
      piece({
        failures: [
          {
            type: "draft",
            code: "boom",
            message: "m",
            triggered_by: null,
            retryable: false,
            cost: 0,
          },
        ],
        activity: [{ label: "draft job running", detail: null, at: null }],
      }),
    );
    expect(failed.status).toBe("failed");
    expect(failed.failedJobs).toBe(1);
  });
});

describe("attentionState", () => {
  it("sums the four human-owed signals", () => {
    const state = attentionState(
      piece({
        open_gaps: 2,
        open_clearances: 1,
        interviews: [
          { interview_id: "i1", assigned_expert: null, status: "open", about: null, is_gap_interview: false },
          { interview_id: "i2", assigned_expert: null, status: "complete", about: null, is_gap_interview: false },
        ],
        failures: [
          { type: "draft", code: "x", message: "m", triggered_by: null, retryable: false, cost: 0 },
        ],
      }),
    );
    expect(state).toMatchObject({ openGaps: 2, openClearances: 1, openInterviews: 1, failedJobs: 1 });
    expect(state.total).toBe(5);
  });

  it("is genuinely clear at zero everywhere", () => {
    expect(attentionState(piece()).total).toBe(0);
  });
});

describe("learningState", () => {
  it("counts lessons by status, tolerating any status string", () => {
    const state = learningState(
      piece({
        lessons: [
          { id: "l1", observed_change: "a", generalizable_rule: "r", status: "proposed" },
          { id: "l2", observed_change: "b", generalizable_rule: "r", status: "accepted" },
          { id: "l3", observed_change: "c", generalizable_rule: "r", status: "rejected" },
          { id: "l4", observed_change: "d", generalizable_rule: "r", status: "proposed" },
        ],
      }),
    );
    expect(state).toEqual({ total: 4, proposed: 2, accepted: 1, rejected: 1 });
  });
});
