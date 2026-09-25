import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { TranscriptPanel } from "@/components/interview/transcript-panel";
import type { TranscriptTurn } from "@/lib/interviews/types";

function turn(overrides: Partial<TranscriptTurn> = {}): TranscriptTurn {
  return {
    id: "t1",
    persona: "ferriss",
    question: "What's the storage workload?",
    answer: "About 10TB.",
    research_derived: false,
    ...overrides,
  };
}

describe("TranscriptPanel", () => {
  it("shows a short answer in full with no clamp/modal control", () => {
    render(
      <TranscriptPanel
        turns={[turn()]}
        editable
        onEdit={vi.fn()}
        onRecap={vi.fn()}
      />,
    );
    expect(screen.getByText("About 10TB.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /full answer/i })).not.toBeInTheDocument();
  });

  it("clamps a genuinely long research-derived answer with a 'Full answer' modal, alongside Recap/Edit", () => {
    const longAnswer = Array.from(
      { length: 60 },
      (_, i) => `Sentence ${i} of a long research-derived answer that keeps going.`,
    ).join(" ");
    render(
      <TranscriptPanel
        turns={[turn({ answer: longAnswer, research_derived: true })]}
        editable
        onEdit={vi.fn()}
        onRecap={vi.fn()}
      />,
    );

    const openModal = screen.getByRole("button", { name: /full answer/i });
    expect(screen.getByRole("button", { name: /^recap$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^edit$/i })).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    fireEvent.click(openModal);
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText(/sentence 59 of a long research/i)).toBeInTheDocument();
  });

  it("edits the complete answer even when the read view is clamped — the textarea is never truncated", () => {
    const longAnswer = Array.from(
      { length: 60 },
      (_, i) => `Sentence ${i} of a long research-derived answer that keeps going.`,
    ).join(" ");
    render(
      <TranscriptPanel
        turns={[turn({ answer: longAnswer })]}
        editable
        onEdit={vi.fn()}
        onRecap={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /^edit$/i }));
    const textarea = screen.getByRole("textbox");
    expect(textarea).toHaveValue(longAnswer);
  });

  it("omits the Full answer control once the interview is complete but keeps Recap available", () => {
    const longAnswer = Array.from(
      { length: 60 },
      (_, i) => `Sentence ${i} of a long research-derived answer that keeps going.`,
    ).join(" ");
    render(
      <TranscriptPanel
        turns={[turn({ answer: longAnswer })]}
        editable={false}
        onEdit={vi.fn()}
        onRecap={vi.fn()}
      />,
    );

    expect(screen.getByRole("button", { name: /full answer/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^recap$/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^edit$/i })).not.toBeInTheDocument();
  });
});
