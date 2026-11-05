import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CouncilRecord } from "@/components/piece-detail/council-record";
import type { CouncilRecord as CouncilRecordData, EditorScore } from "@/lib/pieces/types";

function editorScore(overrides: Partial<EditorScore> = {}): EditorScore {
  return {
    editor: "slop-allergist",
    score: 8.5,
    mandatory: true,
    editorial_fixes: [],
    information_gaps: [],
    clearances: [],
    hard_cap_applied: false,
    ...overrides,
  };
}

function council(overrides: Partial<CouncilRecordData> = {}): CouncilRecordData {
  return {
    round_number: 1,
    iteration: 1,
    revision: "rev-1",
    aggregate: 8.0,
    cost: 0.12,
    stop_reason: null,
    stop_message: null,
    editor_scores: [editorScore()],
    ...overrides,
  };
}

describe("CouncilRecord", () => {
  it("shows the empty state when no council pass has run yet", () => {
    render(<CouncilRecord council={null} />);
    expect(screen.getByText(/no council pass yet/i)).toBeInTheDocument();
  });

  it("shows a dash when an editor has no fixes or gaps", () => {
    render(<CouncilRecord council={council()} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("shows a short list of notes inline with no modal control", () => {
    render(
      <CouncilRecord
        council={council({
          editor_scores: [
            editorScore({ editorial_fixes: ["Tighten the intro paragraph."], information_gaps: ["Need a named customer."] }),
          ],
        })}
      />,
    );
    expect(screen.getByText("Tighten the intro paragraph.")).toBeInTheDocument();
    expect(screen.getByText("Need a named customer.")).toBeInTheDocument();
    expect(screen.getByText("Fix")).toBeInTheDocument();
    expect(screen.getByText("Gap")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /view all/i })).not.toBeInTheDocument();
  });

  it("clamps to a preview plus a modal once an editor returns more than two notes — free-form Opus output has no length ceiling", () => {
    const fixes = ["Fix one.", "Fix two.", "Fix three."];
    const gaps = ["Gap one."];
    render(
      <CouncilRecord
        council={council({ editor_scores: [editorScore({ editorial_fixes: fixes, information_gaps: gaps })] })}
      />,
    );

    // Only the first two items (both fixes, in order) render inline.
    expect(screen.getByText("Fix one.")).toBeInTheDocument();
    expect(screen.getByText("Fix two.")).toBeInTheDocument();
    expect(screen.queryByText("Fix three.")).not.toBeInTheDocument();
    expect(screen.queryByText("Gap one.")).not.toBeInTheDocument();

    const openModal = screen.getByRole("button", { name: /view all 4 notes/i });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    fireEvent.click(openModal);
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText("Fix one.")).toBeInTheDocument();
    expect(within(dialog).getByText("Fix three.")).toBeInTheDocument();
    expect(within(dialog).getByText("Gap one.")).toBeInTheDocument();
  });
});
