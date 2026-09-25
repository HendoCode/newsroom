import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { InterviewSurfaceView } from "@/components/interview/interview-surface-view";
import type { Interview, TranscriptTurn } from "@/lib/interviews/types";
import { WRAPUP_NUDGE_THRESHOLD } from "@/lib/interviews/wrapup";

const PIECE = {
  id: "p1",
  title: "aws-gsi-faq",
  voice: "team",
  owner: "expert@example.com",
  target: null,
};

function interview(overrides: Partial<Interview> = {}): Interview {
  return {
    id: "iv1",
    piece_id: "p1",
    status: "open",
    interviewer_personas: ["ferriss", "skeptic"],
    current_persona_index: 0,
    current_question: null,
    assigned_expert: "you@company",
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

function mockFetch(handlers: Record<string, (init?: RequestInit) => unknown>) {
  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    const key = `${method} ${url}`;
    const handler = handlers[key];
    if (!handler) throw new Error(`unexpected fetch ${key}`);
    return new Response(JSON.stringify(handler(init)), { status: 200 });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("InterviewSurfaceView — the turn flow (D5a/D16b)", () => {
  it("asks the next question, submits an answer, and shows the recap as a confirmation view without overwriting the answer", async () => {
    const withQuestion = interview({ current_question: "What's the real storage workload?" });
    const fetchMock = mockFetch({
      "POST /api/interviews/iv1/next-question": () => withQuestion,
      "POST /api/interviews/iv1/respond": (init) => {
        expect(JSON.parse(String(init?.body))).toEqual({
          text: "About 10TB, roughly $230/month",
        });
        return {
          op: "answer",
          turn: turn({ answer: "About 10TB, roughly $230/month" }),
          recap: "You said the workload is about 10TB at $230/month.",
        };
      },
    });

    render(
      <InterviewSurfaceView
        piece={PIECE}
        initialInterview={interview()}
        initialTurns={[]}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /ask next question/i }));
    expect(await screen.findByText("What's the real storage workload?")).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText(/speak or type your answer/i), {
      target: { value: "About 10TB, roughly $230/month" },
    });
    fireEvent.click(screen.getByRole("button", { name: /submit answer/i }));

    // the recap is a read-only confirmation — never a replacement for the stored answer.
    expect(
      await screen.findByText("You said the workload is about 10TB at $230/month."),
    ).toBeInTheDocument();
    expect(screen.getAllByText("About 10TB, roughly $230/month").length).toBeGreaterThan(0);

    // the "Answer" chip is highlighted as the detected op.
    expect(screen.getByText("Answer")).toHaveClass("bg-foreground");

    // the composer's pending question clears — "Ask next question" resurfaces.
    expect(await screen.findByRole("button", { name: /ask next question/i })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});

describe("InterviewSurfaceView — D6 op surfacing", () => {
  it("surfaces 'research-this' without touching the pending question", async () => {
    mockFetch({
      "POST /api/interviews/iv1/respond": () => ({
        op: "research-this",
        answer: "10TB in S3 Standard is about $230/month.",
        resume_question: "What's the S3 bill?",
      }),
    });

    render(
      <InterviewSurfaceView
        piece={PIECE}
        initialInterview={interview({ current_question: "What's the S3 bill?" })}
        initialTurns={[]}
      />,
    );

    fireEvent.change(screen.getByPlaceholderText(/speak or type your answer/i), {
      target: { value: "/research the S3 pricing" },
    });
    fireEvent.click(screen.getByRole("button", { name: /submit answer/i }));

    expect(
      await screen.findByText("10TB in S3 Standard is about $230/month."),
    ).toBeInTheDocument();
    expect(screen.getByText("Research this")).toHaveClass("bg-foreground");
    // borrowed time, then returned — the pending question is still on screen, composer still up.
    expect(screen.getByText("What's the S3 bill?")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /submit answer/i })).toBeInTheDocument();
  });

  it("surfaces a handled 'meta-command' and resyncs the interview state", async () => {
    const afterSkip = interview({ current_persona_index: 1, current_question: null });
    mockFetch({
      "POST /api/interviews/iv1/respond": () => ({
        op: "meta-command",
        command: "skip",
        handled: true,
        note: null,
      }),
      "GET /api/interviews/iv1": () => afterSkip,
    });

    render(
      <InterviewSurfaceView
        piece={PIECE}
        initialInterview={interview({ current_question: "Q1" })}
        initialTurns={[]}
      />,
    );

    fireEvent.change(screen.getByPlaceholderText(/speak or type your answer/i), {
      target: { value: "let's move to the next interviewer" },
    });
    fireEvent.click(screen.getByRole("button", { name: /submit answer/i }));

    expect(await screen.findByText(/applied: skip/i)).toBeInTheDocument();
    expect(screen.getByText("Session request")).toHaveClass("bg-foreground");
    // resynced: no pending question anymore, so the composer is gone and "Ask next question" is back.
    expect(await screen.findByRole("button", { name: /ask next question/i })).toBeInTheDocument();
  });

  it("surfaces an unhandled meta-command as recorded, never a silent drop", async () => {
    mockFetch({
      "POST /api/interviews/iv1/respond": () => ({
        op: "meta-command",
        command: "switch-piece",
        handled: false,
        note: "aws-gsi-faq",
      }),
      "GET /api/interviews/iv1": () => interview({ current_question: "Q1" }),
    });

    render(
      <InterviewSurfaceView
        piece={PIECE}
        initialInterview={interview({ current_question: "Q1" })}
        initialTurns={[]}
      />,
    );

    fireEvent.change(screen.getByPlaceholderText(/speak or type your answer/i), {
      target: { value: "switch to the aws piece" },
    });
    fireEvent.click(screen.getByRole("button", { name: /submit answer/i }));

    expect(
      await screen.findByText(/noted, not applied here: switch piece — aws-gsi-faq/i),
    ).toBeInTheDocument();
  });

  it("surfaces 'tangent' and reports it was parked to the Vault, never discarded", async () => {
    mockFetch({
      "POST /api/interviews/iv1/respond": () => ({ op: "tangent", spike_id: "spike-123" }),
    });

    render(
      <InterviewSurfaceView
        piece={PIECE}
        initialInterview={interview({ current_question: "Q1" })}
        initialTurns={[]}
      />,
    );

    fireEvent.change(screen.getByPlaceholderText(/speak or type your answer/i), {
      target: { value: "unrelated: we should write about pricing tiers too" },
    });
    fireEvent.click(screen.getByRole("button", { name: /submit answer/i }));

    expect(await screen.findByText(/parked to the vault as spike/i)).toBeInTheDocument();
    expect(screen.getByText("spike-123")).toBeInTheDocument();
    expect(screen.getByText("Tangent")).toHaveClass("bg-foreground");
  });
});

describe("InterviewSurfaceView — skip needs no pending question (Hendo, 2026-08-10)", () => {
  it("skips to the next persona with zero questions ever asked, via advance-persona (never respond)", async () => {
    const afterSkip = interview({ current_persona_index: 1, current_question: null });
    const fetchMock = mockFetch({
      "POST /api/interviews/iv1/advance-persona": (init) => {
        expect(JSON.parse(String(init?.body))).toEqual({ direction: "skip" });
        return { op: "meta-command", command: "skip", handled: true, note: null };
      },
      "GET /api/interviews/iv1": () => afterSkip,
    });

    render(
      <InterviewSurfaceView
        piece={PIECE}
        initialInterview={interview({ current_question: null })}
        initialTurns={[]}
      />,
    );

    // reproduces the exact complaint: nothing has been asked, yet Skip is already clickable.
    const skipButton = screen.getByRole("button", { name: /skip to next persona/i });
    expect(skipButton).toBeEnabled();
    fireEvent.click(skipButton);

    expect(await screen.findByText(/applied: skip/i)).toBeInTheDocument();
    // resynced to the next persona — the conversation panel's own heading, not the persona list.
    expect(await screen.findByRole("heading", { name: "Skeptic" })).toBeInTheDocument();
    // only advance-persona and the resync GET fired — never a respond() call with a made-up answer.
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(
      fetchMock.mock.calls.some(([url]) => String(url).includes("/respond")),
    ).toBe(false);
  });

  it("disables skip once the roster is exhausted", async () => {
    render(
      <InterviewSurfaceView
        piece={PIECE}
        initialInterview={interview({ current_persona_index: 2, current_question: null })}
        initialTurns={[]}
      />,
    );
    expect(screen.getByRole("button", { name: /skip to next persona/i })).toBeDisabled();
  });
});

describe("InterviewSurfaceView — per-persona wrap-up nudge (v1 heuristic)", () => {
  it("shows no nudge before the active persona reaches the question threshold", () => {
    const turns = Array.from({ length: WRAPUP_NUDGE_THRESHOLD - 1 }, (_, i) =>
      turn({ id: `t${i}`, persona: "ferriss" }),
    );
    render(
      <InterviewSurfaceView
        piece={PIECE}
        initialInterview={interview({ current_question: null })}
        initialTurns={turns}
      />,
    );
    expect(screen.queryByText(/has asked a good number of questions/i)).not.toBeInTheDocument();
  });

  it("nudges once the active persona reaches the threshold, without blocking continuing", async () => {
    const turns = Array.from({ length: WRAPUP_NUDGE_THRESHOLD }, (_, i) =>
      turn({ id: `t${i}`, persona: "ferriss" }),
    );
    mockFetch({
      "POST /api/interviews/iv1/next-question": () =>
        interview({ current_question: "One more, if you don't mind" }),
    });

    render(
      <InterviewSurfaceView
        piece={PIECE}
        initialInterview={interview({ current_question: null })}
        initialTurns={turns}
      />,
    );

    expect(await screen.findByText(/has asked a good number of questions/i)).toBeInTheDocument();
    // non-blocking: asking yet another question is still available and still works.
    fireEvent.click(screen.getByRole("button", { name: /ask next question/i }));
    expect(await screen.findByText("One more, if you don't mind")).toBeInTheDocument();
  });

  it("resets for the next persona instead of carrying over the previous persona's count", () => {
    const turns = Array.from({ length: WRAPUP_NUDGE_THRESHOLD + 2 }, (_, i) =>
      turn({ id: `t${i}`, persona: "ferriss" }),
    );
    render(
      <InterviewSurfaceView
        piece={PIECE}
        initialInterview={interview({ current_persona_index: 1, current_question: null })}
        initialTurns={turns}
      />,
    );
    // active persona is now "skeptic", who has asked nothing yet — no nudge despite ferriss's count.
    expect(screen.queryByText(/has asked a good number of questions/i)).not.toBeInTheDocument();
  });
});

describe("InterviewSurfaceView — mark complete is a signal, not the draft trigger (D16a)", () => {
  it("flips the visible status without claiming to trigger drafting", async () => {
    mockFetch({
      "POST /api/interviews/iv1/mark-complete": () => interview({ status: "complete" }),
    });

    render(
      <InterviewSurfaceView
        piece={PIECE}
        initialInterview={interview()}
        initialTurns={[]}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /mark interview complete/i }));

    expect(
      await screen.findByText(/marked complete — the piece owner sees this signal/i),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /mark interview complete/i }),
    ).not.toBeInTheDocument();
  });
});

describe("InterviewSurfaceView — the sacred, editable transcript (D16b)", () => {
  it("edits a stored answer in place and can show an on-demand recap without overwriting it", async () => {
    mockFetch({
      "POST /api/pieces/p1/transcript/turns/t1": (init) => {
        expect(JSON.parse(String(init?.body))).toEqual({
          text: "Actually more like 12TB, I checked the console.",
          interview_id: "iv1",
        });
        return turn({ answer: "Actually more like 12TB, I checked the console." });
      },
      "POST /api/pieces/p1/transcript/turns/t1/recap": () => ({ recap: "You said 12TB." }),
    });

    render(
      <InterviewSurfaceView
        piece={PIECE}
        initialInterview={interview()}
        initialTurns={[turn()]}
      />,
    );

    const panel = screen.getByText("Review & edit my answers").closest("div")!;
    const row = within(panel).getByText("About 10TB.").closest("li")!;
    fireEvent.click(within(row).getByRole("button", { name: /edit/i }));
    const textarea = within(row).getByRole("textbox");
    fireEvent.change(textarea, {
      target: { value: "Actually more like 12TB, I checked the console." },
    });
    fireEvent.click(within(row).getByRole("button", { name: /save/i }));

    await waitFor(() =>
      expect(
        within(panel).getByText("Actually more like 12TB, I checked the console."),
      ).toBeInTheDocument(),
    );
    expect(within(panel).queryByText("About 10TB.")).not.toBeInTheDocument();

    fireEvent.click(within(row).getByRole("button", { name: /recap/i }));
    expect(await within(row).findByText("You said 12TB.")).toBeInTheDocument();
    // the recap is shown alongside, never in place of, the edited answer.
    expect(
      within(panel).getByText("Actually more like 12TB, I checked the console."),
    ).toBeInTheDocument();
  });
});

describe("InterviewSurfaceView — a complete interview's transcript is read-only (2026-08-08)", () => {
  it("offers no edit path once the interview is complete, but recap still works", async () => {
    mockFetch({
      "POST /api/pieces/p1/transcript/turns/t1/recap": () => ({ recap: "You said 10TB." }),
    });

    render(
      <InterviewSurfaceView
        piece={PIECE}
        initialInterview={interview({ status: "complete" })}
        initialTurns={[turn()]}
      />,
    );

    const panel = screen.getByText("Review & edit my answers").closest("div")!;
    expect(within(panel).getByText(/this interview is complete/i)).toBeInTheDocument();
    const row = within(panel).getByText("About 10TB.").closest("li")!;

    // no Edit control at all — not disabled, absent — so there is no way to open the textarea.
    expect(within(row).queryByRole("button", { name: /^edit$/i })).not.toBeInTheDocument();

    // recap remains available: it never writes back over the stored answer.
    fireEvent.click(within(row).getByRole("button", { name: /recap/i }));
    expect(await within(row).findByText("You said 10TB.")).toBeInTheDocument();
  });
});

describe("InterviewSurfaceView — focused mode hides operator chrome & D6 prose (cmw-interview-focused-mode)", () => {
  it("renders no D6 doctrine prose and no add/drop-interviewer roster panel", () => {
    render(
      <InterviewSurfaceView
        piece={PIECE}
        initialInterview={interview({ current_question: "Q1" })}
        initialTurns={[]}
      />,
    );

    // the doctrine paragraph that used to sit under the composer is gone; classification still
    // runs (the "Detected as:" chips remain) but the D6 vocabulary is no longer explained to
    // the interviewee in prose.
    expect(
      screen.queryByText(/free-form input is classified into a bounded op set/i),
    ).not.toBeInTheDocument();
    expect(screen.queryByPlaceholderText(/the machine classifies it/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /interviewers/i })).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /drop .*as an interviewer/i }),
    ).not.toBeInTheDocument();

    // the kept affordances all survive the focus.
    expect(screen.getByText("Q1")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /submit answer/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /skip to next persona/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /mark interview complete/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /stop for the day/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /where are we/i })).toBeInTheDocument();
    expect(screen.getByText("Review & edit my answers")).toBeInTheDocument();
  });
});
