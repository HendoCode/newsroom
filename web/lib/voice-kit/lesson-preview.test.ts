import { describe, expect, it } from "vitest";

import { applyLessonRule } from "@/lib/voice-kit/lesson-preview";

describe("applyLessonRule", () => {
  it("appends a markdown list item, inserting a newline only when the file lacks one", () => {
    expect(applyLessonRule("", "A")).toBe("- A\n");
    expect(applyLessonRule("- existing\n", "A")).toBe("- existing\n- A\n");
    expect(applyLessonRule("- existing", "A")).toBe("- existing\n- A\n");
  });
});
