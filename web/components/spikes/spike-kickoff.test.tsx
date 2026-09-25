import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { SpikeKickoff } from "@/components/spikes/spike-kickoff";
import type { Spike } from "@/lib/spikes/types";

function spike(overrides: Partial<Spike> = {}): Spike {
  return {
    id: "spike-1",
    headline: "You're auditing the wrong line item",
    status: "proposed",
    convergence_score: 0.64,
    creator: "demo-mira@example.com",
    origin: { kind: "oracle-run", ref: "job-1" },
    source_ids: [],
    customer_partner: null,
    outcome_metric: null,
    rank_rationale: "strongest reframe, most shareable",
    convergence_note: null,
    intent: { audience: "technical leaders", angle: "reframe the bill" },
    piece_id: null,
    updated_at: "2026-07-25T00:00:00.000Z",
    ...overrides,
  };
}

const VOICES = ["demo-mira", "demo-dana"];
const PERSONAS = ["ferriss", "skeptic", "customer", "architect"];

const writeText = vi.fn().mockResolvedValue(undefined);

beforeAll(() => {
  Object.defineProperty(navigator, "clipboard", {
    value: { writeText },
    configurable: true,
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
  writeText.mockClear();
});

describe("SpikeKickoff — the pick → assign → interviewer-set → share-link stepper (screen 6)", () => {
  it("pre-selects the default interviewer trio from the available personas", () => {
    vi.stubGlobal("fetch", vi.fn());
    render(<SpikeKickoff spike={spike()} voices={VOICES} personas={PERSONAS} />);
    expect(screen.getByRole("button", { name: "ferriss" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "skeptic" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "customer" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "architect" })).toHaveAttribute("aria-pressed", "false");
  });

  it("defaults Voice to the one carried over from the Radar form, not voices[0] (item 7)", () => {
    vi.stubGlobal("fetch", vi.fn());
    render(
      <SpikeKickoff spike={spike()} voices={VOICES} personas={PERSONAS} radarVoice="demo-dana" />,
    );
    expect(screen.getByLabelText(/voice \(exactly one per piece\)/i)).toHaveValue("demo-dana");
  });

  it("falls back to voices[0] when radarVoice isn't one of this piece's real voices", () => {
    vi.stubGlobal("fetch", vi.fn());
    render(
      <SpikeKickoff spike={spike()} voices={VOICES} personas={PERSONAS} radarVoice="not-a-real-voice" />,
    );
    expect(screen.getByLabelText(/voice \(exactly one per piece\)/i)).toHaveValue("demo-mira");
  });

  it("creates the piece and opens its interview atomically, then copies the link", async () => {
    const fetchMock = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (url === "/api/spikes/spike-1/pick") {
        expect(init?.method).toBe("POST");
        expect(JSON.parse(String(init?.body))).toEqual({
          voice: "demo-mira",
          slug: "you-re-auditing-the-wrong-line-item",
          target: "technical leaders — reframe the bill",
          interviewer_personas: ["ferriss", "skeptic", "customer"],
          assigned_expert: "demo-mira@example.com",
          about: "You're auditing the wrong line item",
        });
        return Promise.resolve({
          ok: true,
          json: async () => ({
            piece_id: "piece-1",
            slug: "you-re-auditing-the-wrong-line-item",
            spike: { ...spike(), status: "picked", piece_id: "piece-1" },
            interview_id: "interview-1",
          }),
        });
      }
      // A piece created via `pick` already has its Interview open
      // (cmw-piece-interviewing-without-interview) — the kickoff screen still checks, the same
      // way it would for a revisited piece, rather than assuming.
      if (url === "/api/pieces/piece-1") {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            interviews: [{ interview_id: "interview-1", status: "open" }],
          }),
        });
      }
      if (url === "/api/interviews/interview-1") {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            id: "interview-1",
            piece_id: "piece-1",
            status: "open",
            interviewer_personas: ["ferriss", "skeptic", "customer"],
            current_persona_index: 0,
            current_question: null,
            assigned_expert: "demo-mira@example.com",
            about: "You're auditing the wrong line item",
            is_gap_interview: false,
          }),
        });
      }
      throw new Error(`unexpected fetch ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<SpikeKickoff spike={spike()} voices={VOICES} personas={PERSONAS} />);

    // Expert must be set BEFORE creating: the Interview opens together with the Piece, using
    // whatever is set here at that moment — there is no later "generate link" step to catch up.
    fireEvent.change(screen.getByLabelText(/assigned expert/i), {
      target: { value: "demo-mira@example.com" },
    });

    fireEvent.click(screen.getByRole("button", { name: "Create piece" }));
    await screen.findByRole("link", { name: "Open piece" });

    const linkInput = await screen.findByLabelText("Interview share link");
    const expectedLink = `${window.location.origin}/interviews/interview-1`;
    expect(linkInput).toHaveValue(expectedLink);
    // Item 8: creating a piece must say so clearly — and now that the Interview opens with it,
    // never point at a stale, no-longer-needed manual "generate the link" step.
    expect(screen.getByText(/interview already open/i)).toBeInTheDocument();
    // A freshly opened link is not announced as a resumed one.
    expect(screen.queryByText(/resuming it instead/i)).not.toBeInTheDocument();
    // The interview is now fixed — no separate "Generate link" control is offered.
    expect(screen.queryByRole("button", { name: "Generate link" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Copy link" }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(expectedLink));

    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("disables Create piece when every interviewer persona is deselected", () => {
    vi.stubGlobal("fetch", vi.fn());
    render(<SpikeKickoff spike={spike()} voices={VOICES} personas={PERSONAS} />);
    for (const name of ["ferriss", "skeptic", "customer"]) {
      fireEvent.click(screen.getByRole("button", { name }));
    }
    expect(screen.getByRole("button", { name: "Create piece" })).toBeDisabled();
  });

  it("resumes an already-open interview instead of offering to fork a new one", async () => {
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url === "/api/pieces/piece-existing") {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            interviews: [
              {
                interview_id: "interview-old",
                assigned_expert: "someone@example.com",
                status: "complete",
                about: "an earlier round",
                is_gap_interview: false,
              },
              {
                interview_id: "interview-open",
                assigned_expert: "demo-mira@example.com",
                status: "open",
                about: "You're auditing the wrong line item",
                is_gap_interview: false,
              },
            ],
          }),
        });
      }
      if (url === "/api/interviews/interview-open") {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            id: "interview-open",
            piece_id: "piece-existing",
            status: "open",
            interviewer_personas: ["ferriss", "skeptic", "customer"],
            current_persona_index: 1,
            current_question: "What broke first?",
            assigned_expert: "demo-mira@example.com",
            about: "You're auditing the wrong line item",
            is_gap_interview: false,
          }),
        });
      }
      throw new Error(`unexpected fetch ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <SpikeKickoff
        spike={spike({ status: "picked", piece_id: "piece-existing" })}
        voices={VOICES}
        personas={PERSONAS}
      />,
    );

    const linkInput = await screen.findByLabelText("Interview share link");
    expect(linkInput).toHaveValue(`${window.location.origin}/interviews/interview-open`);
    expect(screen.getByText(/resuming it instead of starting a new one/i)).toBeInTheDocument();

    // Never forked: no POST to open a second interview was ever made.
    expect(
      fetchMock.mock.calls.some(
        (call) => call[0] === "/api/pieces/piece-existing/interviews",
      ),
    ).toBe(false);
    expect(screen.queryByRole("button", { name: "Generate link" })).not.toBeInTheDocument();
  });

  it("shows an inline error and does not open an interview when pick is rejected", async () => {
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url === "/api/spikes/spike-1/pick") {
        return Promise.resolve({
          ok: false,
          json: async () => ({ error: "spike 'spike-1' is already 'picked' — cannot re-pick" }),
        });
      }
      throw new Error(`unexpected fetch ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<SpikeKickoff spike={spike()} voices={VOICES} personas={PERSONAS} />);
    fireEvent.click(screen.getByRole("button", { name: "Create piece" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/cannot re-pick/i);
    // The piece was never created, so the link step stays disabled — not offered as if it worked.
    expect(screen.getByRole("button", { name: "Generate link" })).toBeDisabled();
  });

  it("skips straight to assign/personas when the spike already has a piece, once the no-open-interview check clears", async () => {
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url === "/api/pieces/piece-existing") {
        return Promise.resolve({ ok: true, json: async () => ({ interviews: [] }) });
      }
      throw new Error(`unexpected fetch ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    render(
      <SpikeKickoff
        spike={spike({ status: "picked", piece_id: "piece-existing" })}
        voices={VOICES}
        personas={PERSONAS}
      />,
    );
    expect(screen.queryByRole("button", { name: "Create piece" })).not.toBeInTheDocument();
    // The existing-interview check runs first (and disables the control while in flight) —
    // only once it clears, finding nothing open, does a plain "Generate link" become available.
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Generate link" })).not.toBeDisabled(),
    );
  });
});

describe("SpikeKickoff — brain unavailable (cmw-boss-facing-presentation, CRITICAL)", () => {
  it("shows the unified brain-unavailable banner instead of 'no voices available'", () => {
    render(<SpikeKickoff spike={spike()} voices={[]} personas={PERSONAS} />);
    expect(screen.queryByText("no voices available")).not.toBeInTheDocument();
    const banner = screen.getByTestId("brain-unavailable-banner");
    expect(banner).toHaveTextContent("Brain unavailable");
    expect(banner).toHaveTextContent("the agents service or the Git brain may be unavailable");
    expect(screen.getByRole("link", { name: /brain setup docs/i })).toBeInTheDocument();
  });

  it("shows the same unified banner instead of 'no personas available'", () => {
    render(<SpikeKickoff spike={spike()} voices={VOICES} personas={[]} />);
    expect(screen.queryByText("no personas available")).not.toBeInTheDocument();
    const banner = screen.getByTestId("brain-unavailable-banner");
    expect(banner).toHaveTextContent("The interviewer persona list can’t be reached");
  });

  it("shows both banners when the whole brain is down (voices and personas empty)", () => {
    render(<SpikeKickoff spike={spike()} voices={[]} personas={[]} />);
    expect(screen.getAllByTestId("brain-unavailable-banner")).toHaveLength(2);
    // And the piece-creation button stays disabled — nothing real can be created.
    expect(screen.getByRole("button", { name: "Create piece" })).toBeDisabled();
  });
});
