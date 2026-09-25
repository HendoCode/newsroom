import { describe, expect, it } from "vitest";

import {
  personaQuestionCount,
  shouldNudgeWrapUp,
  WRAPUP_NUDGE_THRESHOLD,
} from "@/lib/interviews/wrapup";
import type { TranscriptTurn } from "@/lib/interviews/types";

function turn(overrides: Partial<TranscriptTurn> = {}): TranscriptTurn {
  return {
    id: "t1",
    persona: "ferriss",
    question: "Q?",
    answer: "A.",
    research_derived: false,
    ...overrides,
  };
}

function turnsFor(persona: string, count: number): TranscriptTurn[] {
  return Array.from({ length: count }, (_, i) => turn({ id: `t${i}`, persona }));
}

describe("personaQuestionCount", () => {
  it("is zero with no active persona", () => {
    expect(personaQuestionCount([], null, false)).toBe(0);
  });

  it("counts only turns from the active persona, ignoring other personas' turns", () => {
    const turns = [...turnsFor("ferriss", 2), ...turnsFor("skeptic", 3)];
    expect(personaQuestionCount(turns, "ferriss", false)).toBe(2);
  });

  it("adds one for a currently pending (asked, unanswered) question", () => {
    const turns = turnsFor("ferriss", 2);
    expect(personaQuestionCount(turns, "ferriss", true)).toBe(3);
  });
});

describe("shouldNudgeWrapUp", () => {
  it("is false below the threshold", () => {
    const turns = turnsFor("ferriss", WRAPUP_NUDGE_THRESHOLD - 1);
    expect(shouldNudgeWrapUp(turns, "ferriss", false)).toBe(false);
  });

  it("is true once the active persona reaches the threshold", () => {
    const turns = turnsFor("ferriss", WRAPUP_NUDGE_THRESHOLD);
    expect(shouldNudgeWrapUp(turns, "ferriss", false)).toBe(true);
  });

  it("counts a pending question toward the threshold", () => {
    const turns = turnsFor("ferriss", WRAPUP_NUDGE_THRESHOLD - 1);
    expect(shouldNudgeWrapUp(turns, "ferriss", true)).toBe(true);
  });

  it("does not count a different persona's turns toward the active persona's threshold", () => {
    const turns = turnsFor("skeptic", WRAPUP_NUDGE_THRESHOLD + 2);
    expect(shouldNudgeWrapUp(turns, "ferriss", false)).toBe(false);
  });
});
