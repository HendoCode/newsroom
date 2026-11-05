import { describe, expect, it } from "vitest";

import { STAGE_ACTION_REFERENCE } from "@/lib/pieces/actions";
import { BATCH_STAGES, RAIL_STAGES, isBatchStage, railStepStates } from "@/lib/pieces/stage";
import type { PieceStage } from "@/lib/pieces/types";

describe("RAIL_STAGES / isBatchStage — the 10-state machine minus the off-rail `paused`", () => {
  it("lists exactly the 9 non-paused states, in canonical order", () => {
    expect(RAIL_STAGES).toEqual([
      "interviewing",
      "drafting",
      "council",
      "review",
      "incorporating",
      "finalizing",
      "finalized",
      "lessons",
      "released",
    ]);
  });

  it("covers every real PieceStage — unlike STAGE_ACTION_REFERENCE (a Record<PieceStage, string>, " +
    "compiler-enforced complete) or nextAction's exhaustive switch, RAIL_STAGES is a plain array " +
    "checked only with `satisfies readonly PieceStage[]` — that confirms every element is a valid " +
    "stage, never that every stage is an element. A future PieceStage added without also adding it " +
    "here would compile clean and stay green in every other test; this is the one regression test " +
    "that would actually catch it. `published` is a legacy alias of `released` and is not a rail step.", () => {
    const everyRealStage = Object.keys(STAGE_ACTION_REFERENCE).filter((s) => s !== "published").sort();
    const railStagesPlusPaused = [...RAIL_STAGES, "paused"].sort();
    expect(railStagesPlusPaused).toEqual(everyRealStage);
  });

  it("flags exactly the batch (background-job) stages", () => {
    const batch: PieceStage[] = ["drafting", "council", "incorporating", "finalizing"];
    const interactive: PieceStage[] = [
      "interviewing",
      "review",
      "finalized",
      "lessons",
      "paused",
      "released",
      "published",
    ];
    for (const s of batch) expect(isBatchStage(s)).toBe(true);
    for (const s of interactive) expect(isBatchStage(s)).toBe(false);
    expect(BATCH_STAGES.size).toBe(4);
  });
});

describe("railStepStates — current highlighted, everything before it done", () => {
  it("marks steps before the current one done, the current one current, the rest upcoming", () => {
    const states = railStepStates("review");
    expect(states.interviewing).toBe("done");
    expect(states.drafting).toBe("done");
    expect(states.council).toBe("done");
    expect(states.review).toBe("current");
    expect(states.incorporating).toBe("upcoming");
    expect(states.finalizing).toBe("upcoming");
    expect(states.finalized).toBe("upcoming");
    expect(states.lessons).toBe("upcoming");
  });

  it("marks the very first rail stage current with nothing done yet", () => {
    const states = railStepStates("interviewing");
    expect(states.interviewing).toBe("current");
    expect(states.drafting).toBe("upcoming");
  });

  it("marks every rail stage done once the piece reaches the last one", () => {
    const states = railStepStates("released");
    for (const s of RAIL_STAGES.slice(0, -1)) expect(states[s]).toBe("done");
    expect(states.released).toBe("current");
  });

  it("legacy published wire value lights the released rail step", () => {
    const states = railStepStates("published");
    expect(states.released).toBe("current");
  });

  it("paused has no position on the linear rail — no step is current", () => {
    const states = railStepStates("paused");
    for (const s of RAIL_STAGES) expect(states[s]).toBe("upcoming");
  });
});
