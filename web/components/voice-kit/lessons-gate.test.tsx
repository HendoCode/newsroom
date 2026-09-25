import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LessonsGate } from "@/components/voice-kit/lessons-gate";
import type { Lesson } from "@/lib/voice-kit/types";

const LESSONS: Lesson[] = [
  {
    id: "l1",
    voice: "demo-mira",
    source_piece_id: "p1",
    observed_change: "cut the caveat",
    generalizable_rule: "Lead with the number.",
    status: "proposed",
  },
  {
    id: "l2",
    voice: "demo-mira",
    source_piece_id: "p1",
    observed_change: "named the company",
    generalizable_rule: "Prefer a named company over an adjective.",
    status: "proposed",
  },
];

describe("LessonsGate", () => {
  it("keeps per-row accept/edit/reject", () => {
    const onAccept = vi.fn();
    const onReject = vi.fn();
    render(
      <LessonsGate lessons={LESSONS} onAccept={onAccept} onReject={onReject} busyId={null} error={null} />,
    );
    fireEvent.click(within(screen.getByTestId("lesson-l1")).getByRole("button", { name: "Accept" }));
    expect(onAccept).toHaveBeenCalledWith("l1");
    fireEvent.click(within(screen.getByTestId("lesson-l2")).getByRole("button", { name: "Reject" }));
    expect(onReject).toHaveBeenCalledWith("l2");
  });

  it("batch-accepts the selected lessons", () => {
    const onAcceptMany = vi.fn();
    render(
      <LessonsGate
        lessons={LESSONS}
        onAccept={vi.fn()}
        onReject={vi.fn()}
        onAcceptMany={onAcceptMany}
        busyId={null}
        error={null}
      />,
    );
    fireEvent.click(screen.getByRole("checkbox", { name: "Select all proposed lessons" }));
    fireEvent.click(screen.getByRole("button", { name: "Accept 2 selected" }));
    expect(onAcceptMany).toHaveBeenCalledWith(["l1", "l2"]);
  });

  it("previews the Git diff of the rule about to land in content-lessons.md", () => {
    render(
      <LessonsGate
        lessons={[LESSONS[0]!]}
        currentLessonsFile={"- an existing lesson\n"}
        onAccept={vi.fn()}
        onReject={vi.fn()}
        busyId={null}
        error={null}
      />,
    );
    expect(screen.queryByTestId("diff-view")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Preview Git change" }));
    const diff = screen.getByTestId("diff-view");
    expect(diff).toHaveTextContent("- an existing lesson");
    expect(diff).toHaveTextContent("- Lead with the number.");
  });
});
