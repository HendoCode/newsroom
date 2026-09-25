import { describe, expect, it } from "vitest";

import { STAGE_ACTION_REFERENCE, nextAction, secondaryActions } from "@/lib/pieces/actions";
import type { PieceDetail, PieceStage } from "@/lib/pieces/types";

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
    latest_revision: null,
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

describe("nextAction — exactly one stage-contextual primary action, all 10 states covered", () => {
  it("interviewing → the deliberate “enough input” trigger, distinct from mark-complete", () => {
    const action = nextAction(piece({ stage: "interviewing" }));
    expect(action).toEqual({
      kind: "trigger",
      trigger: "enough-input",
      label: "Enough input → draft",
      description: expect.stringContaining("signal"),
    });
  });

  it("interviewing + a failed draft job relabels as Retry but fires the SAME trigger", () => {
    const action = nextAction(
      piece({
        stage: "interviewing",
        failures: [
          { type: "draft", code: "ceiling-exceeded", message: "boom", triggered_by: "you", retryable: false, cost: 0.1 },
        ],
      }),
    );
    expect(action.kind).toBe("trigger");
    expect(action).toMatchObject({ trigger: "enough-input" });
    expect(action.label).toContain("Retry");
  });

  it.each<PieceStage>(["drafting", "council", "incorporating", "finalizing"])(
    "%s is a running batch step — no trigger to fire",
    (stage) => {
      const action = nextAction(piece({ stage }));
      expect(action.kind).toBe("running");
      expect("trigger" in action).toBe(false);
    },
  );

  it("review → a LINK into the dedicated review-round screen, never a blind “reviews done” fire", () => {
    const action = nextAction(piece({ stage: "review", id: "p1" }));
    expect(action).toEqual({
      kind: "link",
      href: "/pieces/p1/review",
      label: "Open review round",
      description: expect.stringContaining("never a blind fire"),
    });
  });

  it("finalized → the primary action is Authorize release (the actual exit from in-flight), regardless of lessons history", () => {
    const action = nextAction(piece({ stage: "finalized", lessons: [] }));
    expect(action).toMatchObject({ kind: "trigger", trigger: "publish", label: "Authorize release" });
    expect(action).not.toHaveProperty("chip");
  });

  it("finalized with pending lessons → Publish stays primary, but carries a chip naming the pending count (Pipeline decision A: equal visual weight, not folded into prose)", () => {
    const action = nextAction(
      piece({
        stage: "finalized",
        lessons: [
          { id: "l1", observed_change: "x", generalizable_rule: "y", status: "proposed" },
          { id: "l2", observed_change: "x", generalizable_rule: "y", status: "accepted" },
        ],
      }),
    );
    expect(action).toMatchObject({
      kind: "trigger",
      trigger: "publish",
      label: "Authorize release",
      chip: { label: "1 lesson awaiting accept/reject" },
    });
  });

  it("lessons with nothing ever proposed → propose, not finish (nothing to accept/edit/reject)", () => {
    const action = nextAction(piece({ stage: "lessons", lessons: [] }));
    expect(action).toEqual({
      kind: "propose-lessons",
      label: "Propose lessons",
      description: expect.any(String),
    });
  });

  it("lessons with unresolved proposals → a link to resolve them, never finish or re-propose", () => {
    const action = nextAction(
      piece({
        stage: "lessons",
        lessons: [
          { id: "l1", observed_change: "x", generalizable_rule: "y", status: "proposed" },
          { id: "l2", observed_change: "x", generalizable_rule: "y", status: "proposed" },
        ],
      }),
    );
    expect(action).toMatchObject({ kind: "link", href: "/voice-kit", label: "Resolve 2 pending lessons" });
  });

  it("lessons with every proposal resolved → finish the D12 gate, the case the old proposed===0 check missed", () => {
    const action = nextAction(
      piece({
        stage: "lessons",
        lessons: [
          { id: "l1", observed_change: "x", generalizable_rule: "y", status: "accepted" },
          { id: "l2", observed_change: "x", generalizable_rule: "y", status: "rejected" },
        ],
      }),
    );
    expect(action).toMatchObject({ kind: "trigger", trigger: "finish-lessons" });
  });

  it("paused → resume", () => {
    const action = nextAction(piece({ stage: "paused" }));
    expect(action).toMatchObject({ kind: "trigger", trigger: "resume", label: "Resume" });
  });

  it("released → Authorize another release (repeatable numbered Publication Releases)", () => {
    const action = nextAction(piece({ stage: "released" }));
    expect(action).toMatchObject({
      kind: "trigger",
      trigger: "publish",
      label: "Authorize another release",
    });
    expect(action.description).toMatch(/immutable numbered/i);
  });
});

describe("secondaryActions — visually distinct, never the primary button", () => {
  it("review offers a Finalize LINK (opens the finalize/outputs screen, never a blind fire) alongside Reviews-done", () => {
    const actions = secondaryActions(piece({ stage: "review" }));
    expect(actions[0]).toEqual({
      kind: "link",
      label: "Finalize",
      href: "/pieces/p1/finalize",
      description: expect.stringContaining("Reviews done"),
    });
    expect(actions[1]).toMatchObject({ kind: "trigger", trigger: "pause" });
  });

  it("review also offers Start-another-round-of-interviews, numbered off the piece's real interview count", () => {
    const noInterviewsYet = secondaryActions(piece({ stage: "review", interviews: [] }));
    expect(noInterviewsYet[2]).toEqual({
      kind: "open-interview-round",
      label: "Start another round of interviews",
      description: expect.stringContaining("round 1"),
      roundNumber: 1,
    });

    const oneRoundAlready = secondaryActions(
      piece({
        stage: "review",
        interviews: [
          { interview_id: "iv1", assigned_expert: null, status: "complete", about: null, is_gap_interview: false },
        ],
      }),
    );
    expect(oneRoundAlready[2]).toMatchObject({ kind: "open-interview-round", roundNumber: 2 });
  });

  it("route-to-interview is never offered outside council/review — no secondary action anywhere else names it", () => {
    for (const stage of [
      "interviewing",
      "drafting",
      "council",
      "incorporating",
      "finalizing",
      "finalized",
      "lessons",
      "paused",
      "released",
      "published",
    ] as PieceStage[]) {
      const actions = secondaryActions(piece({ stage }));
      expect(actions.some((a) => a.kind === "open-interview-round")).toBe(false);
    }
  });

  it("interviewing offers only Stop-for-the-day", () => {
    const actions = secondaryActions(piece({ stage: "interviewing" }));
    expect(actions).toEqual([
      { kind: "trigger", trigger: "pause", label: "Stop for the day", description: expect.any(String) },
    ]);
  });

  it("batch/lessons/paused/published stages offer no secondary actions", () => {
    for (const stage of ["drafting", "council", "incorporating", "finalizing", "lessons", "paused", "released", "published"] as PieceStage[]) {
      expect(secondaryActions(piece({ stage }))).toEqual([]);
    }
  });

  it("finalized offers a Capture-lessons trigger, independent of the Publish primary action", () => {
    const actions = secondaryActions(piece({ stage: "finalized", lessons: [] }));
    expect(actions).toEqual([
      { kind: "trigger", trigger: "capture-lessons", label: "Capture lessons", description: expect.any(String) },
    ]);
  });

  it("finalized with lessons already recorded from an earlier round → capture-lessons notes the history", () => {
    const actions = secondaryActions(
      piece({
        stage: "finalized",
        lessons: [
          { id: "l1", observed_change: "x", generalizable_rule: "y", status: "accepted" },
          { id: "l2", observed_change: "x", generalizable_rule: "y", status: "rejected" },
        ],
      }),
    );
    expect(actions).toMatchObject([{ kind: "trigger", trigger: "capture-lessons" }]);
    expect(actions[0]?.description).toContain("2 lessons recorded");
  });
});

describe("STAGE_ACTION_REFERENCE — the informational stage→action table covers all 10 states", () => {
  it("has an entry for every PieceStage", () => {
    const stages: PieceStage[] = [
      "interviewing",
      "drafting",
      "council",
      "review",
      "incorporating",
      "finalizing",
      "finalized",
      "lessons",
      "paused",
      "released",
      "published",
    ];
    for (const s of stages) expect(STAGE_ACTION_REFERENCE[s]).toEqual(expect.any(String));
  });
});
