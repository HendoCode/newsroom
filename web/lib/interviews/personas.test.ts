import { describe, expect, it } from "vitest";

import { personaLabel, personaRoster } from "@/lib/interviews/personas";
import type { Interview } from "@/lib/interviews/types";

function interview(overrides: Partial<Interview> = {}): Interview {
  return {
    id: "iv1",
    piece_id: "p1",
    status: "open",
    interviewer_personas: ["ferriss", "skeptic", "architect"],
    current_persona_index: 1,
    current_question: "Q?",
    assigned_expert: "you@company",
    about: "AWS GSI technical eval FAQ",
    is_gap_interview: false,
    ...overrides,
  };
}

describe("personaLabel", () => {
  it("title-cases a single-word persona slug", () => {
    expect(personaLabel("ferriss")).toBe("Ferriss");
  });

  it("title-cases each hyphenated word", () => {
    expect(personaLabel("partner-advocate")).toBe("Partner Advocate");
  });
});

describe("personaRoster", () => {
  it("marks personas before current_persona_index as done", () => {
    const roster = personaRoster(interview(), []);
    expect(roster.find((p) => p.name === "ferriss")).toMatchObject({ status: "done" });
  });

  it("marks the persona at current_persona_index as active", () => {
    const roster = personaRoster(interview(), []);
    expect(roster.find((p) => p.name === "skeptic")).toMatchObject({ status: "active" });
  });

  it("marks personas after current_persona_index as suggested (pre-selected, not yet reached)", () => {
    const roster = personaRoster(interview(), []);
    expect(roster.find((p) => p.name === "architect")).toMatchObject({ status: "suggested" });
  });

  it("marks personas not on the interview's roster as off, appended after the roster", () => {
    const allPersonas = ["ferriss", "skeptic", "architect", "barbaro", "customer"];
    const roster = personaRoster(interview(), allPersonas);
    const off = roster.filter((p) => p.status === "off");
    expect(off.map((p) => p.name)).toEqual(["barbaro", "customer"]);
  });

  it("never lists a rostered persona twice even if it also appears in the full roster list", () => {
    const allPersonas = ["ferriss", "skeptic", "architect"];
    const roster = personaRoster(interview(), allPersonas);
    expect(roster).toHaveLength(3);
  });

  it("labels every entry for display", () => {
    const roster = personaRoster(interview(), ["partner-advocate"]);
    expect(roster.find((p) => p.name === "partner-advocate")).toMatchObject({
      label: "Partner Advocate",
      status: "off",
    });
  });
});
