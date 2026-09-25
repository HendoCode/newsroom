import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ResearchGateView } from "@/lib/content-workflow/types";

import { ResearchSection } from "./research-section";

/** Ground truth: the backend enum VALUE (kebab-case), not the frontend union. */
const RECORD_EXPERIENTIAL_WAIVER = "record-experiential-waiver";

function gate(overrides: Partial<ResearchGateView> = {}): ResearchGateView {
  return {
    required: true,
    satisfied: false,
    satisfied_by: null,
    report: null,
    waiver: null,
    ...overrides,
  };
}

function renderSection(overrides: Partial<ResearchGateView> = {}, onChanged = vi.fn()) {
  return render(
    <ResearchSection
      projectId="proj-1"
      research={gate(overrides)}
      projectVersion={3}
      email="operator@example.com"
      onChanged={onChanged}
    />,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ResearchSection", () => {
  it("an unsatisfied gate explains the requirement and offers both paths", () => {
    renderSection();
    expect(
      screen.getByText(/A sourced research report is required before interviews can open/i),
    ).toBeInTheDocument();
    // The report form opens by default on an unsatisfied gate.
    expect(screen.getByPlaceholderText("What was researched")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Record an experiential waiver/ })).toBeInTheDocument();
  });

  it("renders a satisfying report: facts with sources, opinions kept apart, open questions", () => {
    renderSection({
      satisfied: true,
      satisfied_by: "research-report",
      report: {
        content_project_id: "proj-1",
        subject: "Token vs storage economics",
        facts: [
          { statement: "Inference grew 3x faster than training.", source: "Q4 2025 survey" },
        ],
        opinions: [{ statement: "Favors storage-tiering pitches.", holder: "operator@example.com" }],
        open_questions: ["Which segment feels the cost first?"],
        submitted_by: { email: "operator@example.com" },
        created_at: "2026-08-31T06:00:00.000000",
      },
    });
    expect(screen.getByText("Token vs storage economics")).toBeInTheDocument();
    expect(screen.getByText(/Inference grew 3x faster than training\./)).toBeInTheDocument();
    expect(screen.getByText(/Q4 2025 survey/)).toBeInTheDocument();
    expect(screen.getByText(/Favors storage-tiering pitches\./)).toBeInTheDocument();
    expect(screen.getByText("Which segment feels the cost first?")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Add an updated report/ })).toBeInTheDocument();
  });

  it("renders a satisfying waiver with its actor and reason — the record is the audit trail", () => {
    renderSection({
      satisfied: true,
      satisfied_by: "experiential-waiver",
      waiver: {
        content_project_id: "proj-1",
        actor: { subject_id: "operator@example.com", email: "operator@example.com" },
        reason: "I ran this exact migration for three customers last year.",
        recorded_at: "2026-08-31T06:00:00.000000",
      },
    });
    expect(screen.getByText("Experiential waiver recorded")).toBeInTheDocument();
    expect(
      screen.getByText(/I ran this exact migration for three customers last year\./),
    ).toBeInTheDocument();
    expect(screen.getByText(/operator@example\.com/)).toBeInTheDocument();
  });

  it("submitting a report posts the facts-with-sources shape and reloads", async () => {
    const onChanged = vi.fn();
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 201,
      json: async () => ({ id: "rep-1" }),
    });
    vi.stubGlobal("fetch", fetchMock);
    renderSection({}, onChanged);

    fireEvent.change(screen.getByPlaceholderText("What was researched"), {
      target: { value: "Token vs storage economics" },
    });
    // First fact row exists by default; the first row's inputs are the required pair.
    const factInputs = screen.getAllByPlaceholderText("Fact");
    const sourceInputs = screen.getAllByPlaceholderText("Source");
    const firstFact = factInputs[0];
    const firstSource = sourceInputs[0];
    if (!firstFact || !firstSource) throw new Error("expected the default fact row");
    fireEvent.change(firstFact, { target: { value: "Inference grew 3x faster." } });
    fireEvent.change(firstSource, { target: { value: "Q4 2025 survey" } });

    fireEvent.click(screen.getByRole("button", { name: /Save research report/ }));

    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/content-workflow/proj-1/research-report");
    const body = JSON.parse(String(init.body));
    expect(body.subject).toBe("Token vs storage economics");
    expect(body.facts).toEqual([
      { statement: "Inference grew 3x faster.", source: "Q4 2025 survey" },
    ]);
    expect(body.submitted_by.email).toBe("operator@example.com");
  });

  it("recording a waiver submits the real command envelope with actor and reason", async () => {
    const onChanged = vi.fn();
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ outcome: "applied" }),
    });
    vi.stubGlobal("fetch", fetchMock);
    renderSection({}, onChanged);

    fireEvent.click(screen.getByRole("button", { name: /Record an experiential waiver/ }));
    fireEvent.change(
      screen.getByPlaceholderText(/Why your experience covers this subject/),
      { target: { value: "I delivered this exact migration myself." } },
    );
    fireEvent.click(screen.getByRole("button", { name: /Record waiver/ }));

    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/content-workflow/submit");
    const envelope = JSON.parse(String(init.body));
    expect(envelope.command_type).toBe(RECORD_EXPERIENTIAL_WAIVER);
    expect(envelope.aggregate).toEqual({ kind: "content-project", id: "proj-1" });
    expect(envelope.expected_version).toBe(3);
    expect(envelope.actor.email).toBe("operator@example.com");
    expect(envelope.payload.type).toBe(RECORD_EXPERIENTIAL_WAIVER);
    expect(envelope.payload.content_project_id).toBe("proj-1");
    expect(envelope.payload.reason).toBe("I delivered this exact migration myself.");
  });

  it("a rejected waiver surfaces the rejection message, not a silent failure", async () => {
    const onChanged = vi.fn();
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        outcome: "rejected",
        rejection: { code: "version-conflict", message: "the project changed after it was inspected" },
      }),
    });
    vi.stubGlobal("fetch", fetchMock);
    renderSection({}, onChanged);

    fireEvent.click(screen.getByRole("button", { name: /Record an experiential waiver/ }));
    fireEvent.change(
      screen.getByPlaceholderText(/Why your experience covers this subject/),
      { target: { value: "reason" } },
    );
    fireEvent.click(screen.getByRole("button", { name: /Record waiver/ }));

    await waitFor(() =>
      expect(screen.getByText(/the project changed after it was inspected/)).toBeInTheDocument(),
    );
    expect(onChanged).not.toHaveBeenCalled();
  });
});
