import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TranscriptRecord } from "@/components/piece-detail/transcript-record";
import type { TranscriptTurn } from "@/lib/interviews/types";
import type { InterviewRecord } from "@/lib/pieces/types";

function interviewRecord(overrides: Partial<InterviewRecord> = {}): InterviewRecord {
  return {
    interview_id: "iv1",
    assigned_expert: "expert@example.com",
    status: "open",
    about: "AWS GSI technical eval FAQ",
    is_gap_interview: false,
    ...overrides,
  };
}

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

describe("TranscriptRecord", () => {
  it("shows fallbacks when the piece has no interviews and no turns yet", () => {
    render(<TranscriptRecord interviews={[]} turns={[]} />);
    expect(screen.getByText(/no interviews opened yet/i)).toBeInTheDocument();
    expect(screen.getByText(/no interview turns recorded yet/i)).toBeInTheDocument();
    // No origin spike to route back to (e.g. a Piece with no origin Spike at all) — no dead link.
    expect(screen.queryByRole("link", { name: /open the kickoff screen/i })).not.toBeInTheDocument();
  });

  it("routes back to the kickoff screen when a piece has zero interviews but a known origin spike (cmw-piece-interviewing-without-interview: the only route back for a piece stuck this way)", () => {
    render(<TranscriptRecord interviews={[]} turns={[]} originSpikeId="spike-1" />);
    const link = screen.getByRole("link", { name: /open the kickoff screen/i });
    expect(link).toHaveAttribute("href", "/spikes/spike-1");
  });

  it("offers a resume link only for an open interview, never a completed one", () => {
    render(
      <TranscriptRecord
        interviews={[
          interviewRecord({ interview_id: "iv-open", status: "open" }),
          interviewRecord({ interview_id: "iv-done", status: "complete", about: "Gap follow-up" }),
        ]}
        turns={[turn()]}
      />,
    );

    const resumeLinks = screen.getAllByRole("link", { name: /resume interview/i });
    expect(resumeLinks).toHaveLength(1);
    expect(resumeLinks[0]).toHaveAttribute("href", "/interviews/iv-open");
    expect(screen.getByText("complete")).toBeInTheDocument();
  });

  it("renders every turn read-only — no edit or recap control exists on this view", () => {
    render(
      <TranscriptRecord
        interviews={[interviewRecord({ status: "complete" })]}
        turns={[turn(), turn({ id: "t2", question: "Any gotchas?", answer: "A few." })]}
      />,
    );

    expect(screen.getByText("About 10TB.")).toBeInTheDocument();
    expect(screen.getByText("A few.")).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /edit/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /recap/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /resume interview/i })).not.toBeInTheDocument();
  });

  it("marks a gap interview distinctly", () => {
    render(
      <TranscriptRecord
        interviews={[interviewRecord({ is_gap_interview: true })]}
        turns={[]}
      />,
    );
    expect(screen.getByText("gap")).toBeInTheDocument();
  });

  it("numbers interview sessions as rounds in the order given (creation order, per the backend's now-sorted by_piece)", () => {
    render(
      <TranscriptRecord
        interviews={[
          interviewRecord({ interview_id: "iv1", about: "Initial kickoff" }),
          interviewRecord({ interview_id: "iv2", about: "Follow-up", is_gap_interview: true }),
        ]}
        turns={[]}
      />,
    );
    expect(screen.getByText("Round 1")).toBeInTheDocument();
    expect(screen.getByText("Round 2")).toBeInTheDocument();
  });

  it("admits turns can't be attributed to a specific round once there's more than one, rather than implying an attribution the data doesn't support", () => {
    const { rerender } = render(
      <TranscriptRecord interviews={[interviewRecord({ interview_id: "iv1" })]} turns={[turn()]} />,
    );
    expect(screen.queryByText(/can.t be split out per round/i)).not.toBeInTheDocument();

    rerender(
      <TranscriptRecord
        interviews={[
          interviewRecord({ interview_id: "iv1" }),
          interviewRecord({ interview_id: "iv2", is_gap_interview: true }),
        ]}
        turns={[turn()]}
      />,
    );
    expect(screen.getByText(/can.t be split out per round/i)).toBeInTheDocument();
  });

  it("shows a short answer in full with no clamp/modal control", () => {
    render(<TranscriptRecord interviews={[]} turns={[turn({ answer: "About 10TB." })]} />);
    expect(screen.getByText("About 10TB.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /read full answer/i })).not.toBeInTheDocument();
  });

  it("clamps a genuinely long research-derived answer with a modal for the full text (Hendo's ask: 'a modal popup of the complete text')", () => {
    const longAnswer = Array.from(
      { length: 60 },
      (_, i) => `Sentence ${i} of a long research-derived answer that keeps going.`,
    ).join(" ");
    render(
      <TranscriptRecord
        interviews={[]}
        turns={[turn({ answer: longAnswer, research_derived: true })]}
      />,
    );

    const openModal = screen.getByRole("button", { name: /read full answer/i });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    fireEvent.click(openModal);
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText(new RegExp(`sentence 59 of a long research`, "i"))).toBeInTheDocument();
  });
});
