import { describe, expect, it } from "vitest";

import { needsMyAction } from "@/lib/dashboard/needs-my-action";
import type { QueueItem } from "@/lib/dashboard/types";

const ME = "me@example.com";
const OTHER = "someone@example.com";

/** A neutral piece with no branch satisfied; override per test. */
function piece(overrides: Partial<QueueItem> = {}): QueueItem {
  return {
    kind: "piece",
    id: "p1",
    title: "A piece",
    voice: "demo-mira",
    stage: "drafting",
    spike_status: null,
    owner: OTHER,
    assigned_experts: [],
    creator: null,
    council_aggregate: null,
    open_gaps: 0,
    open_clearances: 0,
    review_round: null,
    open_interviews: [],
    has_complete_interview: false,
    failed_job: null,
    lessons_proposed: 0,
    spike_assigned: false,
    updated_at: null,
    last_human_touch_at: null,
    ...overrides,
  };
}

function spike(overrides: Partial<QueueItem> = {}): QueueItem {
  return piece({
    kind: "spike",
    id: "s1",
    title: "A spike",
    voice: null,
    stage: null,
    spike_status: "proposed",
    owner: null,
    creator: OTHER,
    ...overrides,
  });
}

describe("needsMyAction — expanded attribution branches (Item 3)", () => {
  it("branch 1: assigned expert on an open interview", () => {
    const item = piece({
      stage: "interviewing",
      open_interviews: [{ interview_id: "iv1", expert: ME }],
    });
    expect(needsMyAction(ME, item)?.relationship).toBe("assigned-expert");
  });

  it("branch 1 does NOT match an interview assigned to someone else", () => {
    const item = piece({
      stage: "interviewing",
      open_interviews: [{ interview_id: "iv1", expert: OTHER }],
    });
    expect(needsMyAction(ME, item)).toBeNull();
  });

  it("branch 2: assigned expert invited but no open interview yet (unanswered invite)", () => {
    const item = piece({
      stage: "interviewing",
      owner: OTHER,
      assigned_experts: [ME],
      open_interviews: [],
    });
    expect(needsMyAction(ME, item)?.relationship).toBe("assigned-expert");
  });

  it("branch 2 does NOT match once an open interview exists for you", () => {
    const item = piece({
      stage: "interviewing",
      owner: OTHER,
      assigned_experts: [ME],
      open_interviews: [{ interview_id: "iv1", expert: ME }],
    });
    // Branch 1 takes over; the result is still assigned-expert, but for the open-interview reason.
    expect(needsMyAction(ME, item)?.relationship).toBe("assigned-expert");
  });

  it("branch 2 does NOT match when you are not among assigned experts", () => {
    const item = piece({
      stage: "interviewing",
      owner: OTHER,
      assigned_experts: [OTHER],
      open_interviews: [],
    });
    expect(needsMyAction(ME, item)).toBeNull();
  });

  it("branch 3: owner decides 'enough input' once an interview is marked complete", () => {
    const item = piece({ stage: "interviewing", owner: ME, has_complete_interview: true });
    expect(needsMyAction(ME, item)?.relationship).toBe("owner");
  });

  it("branch 3 does NOT match while no interview is complete", () => {
    const item = piece({ stage: "interviewing", owner: ME, has_complete_interview: false });
    expect(needsMyAction(ME, item)).toBeNull();
  });

  it("branch 4: owner of a piece routed back to interviewing with open GAPs", () => {
    const item = piece({ stage: "interviewing", owner: ME, open_gaps: 3 });
    expect(needsMyAction(ME, item)?.relationship).toBe("owner");
  });

  it("branch 4 does NOT match an interviewing piece with zero open GAPs", () => {
    const item = piece({ stage: "interviewing", owner: ME, open_gaps: 0 });
    expect(needsMyAction(ME, item)).toBeNull();
  });

  it("branch 5: owner of a piece in review", () => {
    const item = piece({ stage: "review", owner: ME });
    expect(needsMyAction(ME, item)?.relationship).toBe("owner");
  });

  it("branch 6: a failed/stuck job the user triggered — any stage, taking priority", () => {
    const item = piece({
      stage: "interviewing", // stayed at last stable stage; flag not roll-back (Item 4)
      owner: ME,
      failed_job: {
        type: "draft",
        code: "ceiling-exceeded",
        message: "ceiling",
        triggered_by: ME,
        retryable: false,
        cost: 0.12,
      },
    });
    expect(needsMyAction(ME, item)?.relationship).toBe("last-actor");
  });

  it("branch 6 does NOT match a failed job someone else triggered", () => {
    const item = piece({
      failed_job: {
        type: "draft",
        code: "x",
        message: "m",
        triggered_by: OTHER,
        retryable: false,
        cost: 0,
      },
    });
    expect(needsMyAction(ME, item)).toBeNull();
  });

  it("branch 7: owner of a piece being incorporated", () => {
    const item = piece({ stage: "incorporating", owner: ME });
    expect(needsMyAction(ME, item)?.relationship).toBe("owner");
  });

  it("branch 8: owner of a paused piece", () => {
    const item = piece({ stage: "paused", owner: ME });
    expect(needsMyAction(ME, item)?.relationship).toBe("owner");
  });

  it("branch 9: owner of a finalized piece with proposed, unreviewed lessons", () => {
    const item = piece({ stage: "finalized", owner: ME, lessons_proposed: 5 });
    expect(needsMyAction(ME, item)?.relationship).toBe("owner");
  });

  it("branch 10: owner of a finalized piece with no pending lessons is publish-ready", () => {
    const item = piece({ stage: "finalized", owner: ME, lessons_proposed: 0 });
    expect(needsMyAction(ME, item)?.relationship).toBe("owner");
    expect(needsMyAction(ME, item)?.why).toMatch(/publish/i);
  });

  it("branch 11: owner of a piece in the lessons stage", () => {
    const item = piece({ stage: "lessons", owner: ME, lessons_proposed: 2 });
    expect(needsMyAction(ME, item)?.relationship).toBe("owner");
  });

  it("a published piece never needs my action — terminal, nothing left to do", () => {
    const item = piece({ stage: "published", owner: ME, lessons_proposed: 5 });
    expect(needsMyAction(ME, item)).toBeNull();
  });

  it("branch 12: coordinator on a picked-but-unassigned spike they created", () => {
    const item = spike({ spike_status: "picked", spike_assigned: false, creator: ME });
    expect(needsMyAction(ME, item)?.relationship).toBe("coordinator");
  });

  it("branch 12 does NOT match once the spike is assigned", () => {
    const item = spike({ spike_status: "picked", spike_assigned: true, creator: ME });
    expect(needsMyAction(ME, item)).toBeNull();
  });

  it("branch 12 does NOT match a merely proposed spike", () => {
    const item = spike({ spike_status: "proposed", creator: ME });
    expect(needsMyAction(ME, item)).toBeNull();
  });
});

describe("needsMyAction — flat authorization (never a gate)", () => {
  it("returns null for a teammate's piece — but this is NOT a denial of access", () => {
    // The predicate only answers 'is it on MY plate'; the teammate's review piece stays in the
    // shared queue and is fully actionable from 'All in flight'.
    const item = piece({ stage: "review", owner: OTHER });
    expect(needsMyAction(ME, item)).toBeNull();
  });

  it("returns null for a blank/absent viewer email", () => {
    const item = piece({ stage: "review", owner: ME });
    expect(needsMyAction(null, item)).toBeNull();
    expect(needsMyAction(undefined, item)).toBeNull();
    expect(needsMyAction("", item)).toBeNull();
  });

  it("carries a human-readable 'why' line for the matched relationship", () => {
    const item = piece({ stage: "review", owner: ME });
    expect(needsMyAction(ME, item)?.why).toMatch(/review/i);
  });
});
