import { describe, expect, it } from "vitest";

import {
  buildInbox,
  DECISION_GROUPS,
  decisionGroupFor,
  libraryPieces,
  librarySummary,
  machineWorking,
} from "@/lib/dashboard/desk";
import { needsMyAction } from "@/lib/dashboard/needs-my-action";
import type { QueueItem } from "@/lib/dashboard/types";

const ME = "me@example.com";
const OTHER = "someone@example.com";

/** A neutral piece that satisfies NO predicate branch; override per fixture. */
function piece(overrides: Partial<QueueItem> = {}): QueueItem {
  return {
    kind: "piece",
    id: Math.random().toString(36).slice(2),
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
    title: "A spike",
    voice: null,
    stage: null,
    spike_status: "proposed",
    owner: null,
    creator: OTHER,
    ...overrides,
  });
}

const FAILED_BY_ME = {
  type: "draft",
  code: "boom",
  message: "it broke",
  triggered_by: ME,
  retryable: true,
  cost: 0.01,
} as const;

/** One fixture per predicate branch (needs-my-action.ts), labeled for the mapping tests. */
function branchFixtures(): { label: string; item: QueueItem; expected: string | null }[] {
  return [
    {
      label: "branch 1 — assigned expert on an open interview",
      item: piece({ stage: "interviewing", open_interviews: [{ interview_id: "iv1", expert: ME }] }),
      expected: "answer",
    },
    {
      label: "branch 2 — assigned expert invited, no open interview yet",
      item: piece({ stage: "interviewing", assigned_experts: [ME], open_interviews: [] }),
      expected: "answer",
    },
    {
      label: "branch 3 — owner deciding enough input (complete interview)",
      item: piece({ stage: "interviewing", owner: ME, has_complete_interview: true }),
      expected: "enough-input",
    },
    {
      label: "branch 4 — owner with GAPs looped back from review",
      item: piece({ stage: "interviewing", owner: ME, open_gaps: 2 }),
      expected: "enough-input",
    },
    {
      label: "branch 5 — owner of a piece in review",
      item: piece({ stage: "review", owner: ME }),
      expected: "review-round",
    },
    {
      label: "branch 6 — failed job the user triggered (checked first, dominates the stage)",
      item: piece({ stage: "review", owner: ME, failed_job: { ...FAILED_BY_ME } }),
      expected: "recover",
    },
    {
      label: "branch 7 — owner of an incorporating piece is NOT a decision; it is machine work",
      item: piece({ stage: "incorporating", owner: ME }),
      expected: null,
    },
    {
      label: "branch 8 — owner of a paused piece",
      item: piece({ stage: "paused", owner: ME }),
      expected: "resume",
    },
    {
      label: "branch 9 — finalized owner with proposed lessons",
      item: piece({ stage: "finalized", owner: ME, lessons_proposed: 2 }),
      expected: "lessons",
    },
    {
      label: "branch 10 — finalized owner, publish-ready",
      item: piece({ stage: "finalized", owner: ME, lessons_proposed: 0 }),
      expected: "sign-off",
    },
    {
      label: "branch 11 — owner of a piece in the lessons stage",
      item: piece({ stage: "lessons", owner: ME }),
      expected: "lessons",
    },
    {
      label: "branch 12 — picked-but-unassigned spike the user created",
      item: spike({ spike_status: "picked", spike_assigned: false, creator: ME }),
      expected: "pick-spike",
    },
  ];
}

describe("decisionGroupFor — every predicate branch maps to exactly the settled decision", () => {
  for (const { label, item, expected } of branchFixtures()) {
    it(label, () => {
      const needs = needsMyAction(ME, item);
      expect(needs).not.toBeNull(); // fixture sanity: this really is a predicate hit
      expect(decisionGroupFor(item, needs!)).toBe(expected);
    });
  }

  it("the failed-job branch dominates even when another branch also applies", () => {
    // Interviewing + my open interview (branch 1) AND a failed job I triggered (branch 6):
    // the predicate checks failed_job first, so the group must be recover, not answer.
    const item = piece({
      stage: "interviewing",
      open_interviews: [{ interview_id: "iv1", expert: ME }],
      failed_job: { ...FAILED_BY_ME },
    });
    const needs = needsMyAction(ME, item);
    expect(needs?.relationship).toBe("last-actor");
    expect(decisionGroupFor(item, needs!)).toBe("recover");
  });
});

describe("buildInbox / machineWorking — nothing the predicate surfaces is dropped", () => {
  it("every predicate hit lands in EXACTLY ONE of the inbox or the machine strip", () => {
    const battery = [
      ...branchFixtures().map((f) => f.item),
      // Non-hits that must stay out of the inbox entirely:
      piece({ stage: "drafting", owner: ME }), // batch stage, no predicate branch for owner
      piece({ stage: "published", owner: ME }), // terminal — library only
      piece({ stage: "review", owner: OTHER }), // someone else's review
      piece({ stage: "incorporating", owner: OTHER, failed_job: { ...FAILED_BY_ME, triggered_by: OTHER } }),
      spike({ spike_status: "proposed" }),
    ];
    const strip = machineWorking(battery);
    const inbox = buildInbox(battery, ME);
    const inboxItems = inbox.flatMap((g) => g.entries.map((e) => e.item));

    for (const item of battery) {
      const needs = needsMyAction(ME, item);
      const inInbox = inboxItems.includes(item);
      const inStrip = strip.includes(item);
      if (needs === null) {
        expect(inInbox, "non-hits never reach the inbox").toBe(false);
      } else {
        expect(inInbox || inStrip, `predicate hit lost: ${item.stage}/${item.kind}`).toBe(true);
        expect(inInbox && inStrip, "an item is either a decision or machine movement, not both").toBe(false);
      }
    }
  });

  it("groups entries by decision in the settled DECISION_GROUPS order, not item order", () => {
    const recover = piece({ stage: "interviewing", failed_job: { ...FAILED_BY_ME } });
    const answer = piece({ stage: "interviewing", open_interviews: [{ interview_id: "iv", expert: ME }] });
    const signOff = piece({ stage: "finalized", owner: ME });
    const groups = buildInbox([recover, answer, signOff], ME);
    expect(groups.map((g) => g.def.key)).toEqual(["answer", "sign-off", "recover"]);
    expect(groups.map((g) => g.entries.length)).toEqual([1, 1, 1]);
  });

  it("omits empty groups and returns [] for a falsy email", () => {
    const items = [piece({ stage: "review", owner: ME })];
    expect(buildInbox(items, ME).map((g) => g.def.key)).toEqual(["review-round"]);
    expect(buildInbox(items, null)).toEqual([]);
    expect(buildInbox(items, "")).toEqual([]);
  });

  it("entries carry the predicate's own why/relationship through unchanged", () => {
    const item = piece({ stage: "review", owner: ME });
    const groups = buildInbox([item], ME);
    const first = groups[0];
    expect(first).toBeDefined();
    expect(first!.entries[0]!.needs).toEqual(needsMyAction(ME, item));
  });
});

describe("machineWorking — ambient running work, never a failed or finished piece", () => {
  it("includes only batch-stage pieces with no failed job", () => {
    const drafting = piece({ stage: "drafting" });
    const council = piece({ stage: "council", owner: OTHER });
    const incorporating = piece({ stage: "incorporating", owner: ME });
    const finalizing = piece({ stage: "finalizing" });
    const items = [
      drafting,
      council,
      incorporating,
      finalizing,
      piece({ stage: "review" }), // human stage
      piece({ stage: "paused" }), // off-rail
      piece({ stage: "published" }), // terminal
      piece({ stage: "council", failed_job: { ...FAILED_BY_ME } }), // stopped, not running
      spike({ spike_status: "in-flight" }), // not a piece
    ];
    expect(machineWorking(items)).toEqual([drafting, council, incorporating, finalizing]);
  });
});

describe("libraryPieces / librarySummary — the honest all-pieces view", () => {
  it("library is pieces only — spikes live on their own page", () => {
    const p = piece({ stage: "published" });
    const s = spike({ spike_status: "vaulted" });
    expect(libraryPieces([p, s])).toEqual([p]);
  });

  it("summary counts in-flight / done / failed via statusOf, never conflating them", () => {
    const items = [
      piece({ stage: "interviewing" }), // in flight
      piece({ stage: "incorporating" }), // in flight (a running job is still in-flight work)
      piece({ stage: "finalized" }), // done
      piece({ stage: "published" }), // done — the count the old "All in flight" tab lied about
      piece({ stage: "drafting", failed_job: { ...FAILED_BY_ME } }), // failed
      spike({ spike_status: "proposed" }), // not a piece, excluded entirely
    ];
    expect(librarySummary(items)).toEqual({ total: 5, inFlight: 2, done: 2, failed: 1 });
  });
});

describe("DECISION_GROUPS — the settled display metadata", () => {
  it("declares every group exactly once, in display order", () => {
    expect(DECISION_GROUPS.map((g) => g.key)).toEqual([
      "answer",
      "enough-input",
      "review-round",
      "sign-off",
      "lessons",
      "recover",
      "pick-spike",
      "resume",
    ]);
    for (const g of DECISION_GROUPS) {
      expect(g.label.length).toBeGreaterThan(0);
      expect(g.description.length).toBeGreaterThan(0);
    }
  });
});
