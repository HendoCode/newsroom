import { describe, expect, it } from "vitest";

import {
  humanizeSlug,
  obligationKindLabel,
  OBLIGATION_KIND_LABELS,
  phaseLabel,
  pieceRoleLabel,
} from "./labels";
import type { HumanObligationKind } from "./types";

const ALL_KINDS = Object.keys(OBLIGATION_KIND_LABELS) as HumanObligationKind[];

describe("content-workflow operator-facing labels", () => {
  it("never greets a teammate with a raw enum/slug for any obligation kind", () => {
    for (const kind of ALL_KINDS) {
      const label = obligationKindLabel(kind);
      expect(label, kind).not.toBe(kind);
      expect(label, kind).not.toMatch(/[_]/);
      expect(label, kind).not.toMatch(/HumanObligation|CommandKind/i);
    }
  });

  it("humanizes unknown slugs rather than echoing them", () => {
    expect(humanizeSlug("confirm-input-sufficiency")).toBe("Confirm input sufficiency");
    expect(phaseLabel("producing")).toBe("Producing");
    expect(phaseLabel("quality-closure")).toBe("In review");
    expect(pieceRoleLabel("anchor")).toBe("Main piece");
    expect(pieceRoleLabel("derivative")).toBe("Follow-on piece");
  });
});
