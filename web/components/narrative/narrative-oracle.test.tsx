import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { NarrativeOracle } from "@/components/narrative/narrative-oracle";

afterEach(() => {
  vi.unstubAllGlobals();
});

beforeEach(() => {
  const localStorageMock = {
    getItem: vi.fn(() => null),
    setItem: vi.fn(),
  };
  vi.stubGlobal("localStorage", localStorageMock);
});

describe("NarrativeOracle — Entry A/B → Oracle run → ranked spikes preview (screen 8)", () => {
  it("Entry B: creates a Narrative, then runs the Oracle against it", async () => {
    const fetchMock = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (url === "/api/narratives") {
        expect(JSON.parse(String(init?.body))).toEqual({
          seed_text: "S3 is maligned as the most expensive storage on earth",
          audience: "technical leaders",
          angle: "reframe the bill",
        });
        return Promise.resolve({ ok: true, json: async () => ({ id: "narrative-1" }) });
      }
      if (url === "/api/oracle/run") {
        expect(JSON.parse(String(init?.body))).toEqual({
          entry_mode: "narrative",
          voice: "demo-mira",
          lookback_days: 7,
          narrative_id: "narrative-1",
        });
        return Promise.resolve({
          ok: true,
          json: async () => ({ job_id: "job-123", status: "succeeded", cost_usd: 0.05, error: null }),
        });
      }
      if (url.includes("/api/spikes")) {
        // expect query params origin_ref and origin_kind
        expect(url).toContain("origin_ref=job-123");
        expect(url).toContain("origin_kind=oracle-run");
        return Promise.resolve({
          ok: true,
          json: async () => ({
            source: "store",
            items: [
              {
                id: "spike-1",
                headline: "Token cost vs. storage cost, drawn to scale",
                status: "proposed",
                convergence_score: 0.71,
                creator: "demo-mira@example.com",
                origin: { kind: "narrative", ref: "narrative-1" },
                source_ids: [],
                customer_partner: "AWS",
                outcome_metric: "~130x token vs S3",
                rank_rationale: null,
                convergence_note: null,
                intent: null,
                piece_id: null,
                updated_at: "2026-07-25T00:00:00.000Z",
              },
            ],
          }),
        });
      }
      throw new Error(`unexpected fetch ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<NarrativeOracle voices={["demo-mira", "demo-dana"]} authorEmail="you@example.com" />);

    fireEvent.change(screen.getByLabelText("Narrative"), {
      target: { value: "S3 is maligned as the most expensive storage on earth" },
    });
    fireEvent.change(screen.getByLabelText("Audience"), { target: { value: "technical leaders" } });
    fireEvent.change(screen.getByLabelText("Angle intent"), { target: { value: "reframe the bill" } });

    fireEvent.click(screen.getByRole("button", { name: /run radar/i }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    // The explicit success readout (cmw-boss-facing-presentation, MEDIUM) names the outcome.
    expect(await screen.findByText(/radar run complete — job job-123/i)).toBeInTheDocument();
    expect(screen.getByText("Token cost vs. storage cost, drawn to scale")).toBeInTheDocument();
  });

  it("Entry A: runs an open scan with no narrative, skipping narrative creation", async () => {
    const fetchMock = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (url === "/api/oracle/run") {
        expect(JSON.parse(String(init?.body))).toEqual({
          entry_mode: "open-scan",
          voice: "demo-mira",
          lookback_days: 7,
          narrative_id: null,
        });
        return Promise.resolve({
          ok: true,
          json: async () => ({ job_id: "job-456", status: "succeeded", cost_usd: 0.02, error: null }),
        });
      }
      if (url.includes("/api/spikes")) {
        expect(url).toContain("origin_ref=job-456");
        expect(url).toContain("origin_kind=oracle-run");
        return Promise.resolve({ ok: true, json: async () => ({ source: "seed", items: [] }) });
      }
      throw new Error(`unexpected fetch ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<NarrativeOracle voices={["demo-mira"]} authorEmail="you@example.com" />);

    fireEvent.click(screen.getByRole("button", { name: /entry a — open scan/i }));
    fireEvent.click(screen.getByRole("button", { name: /^run radar$/i }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(fetchMock.mock.calls.map(([url]) => url)).not.toContain("/api/narratives");
  });

  it("shows an inline error when the narrative create fails and never runs the Oracle", async () => {
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url === "/api/narratives") {
        return Promise.resolve({ ok: false, json: async () => ({ error: "seed_text is required" }) });
      }
      throw new Error(`unexpected fetch ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<NarrativeOracle voices={["demo-mira"]} authorEmail="you@example.com" />);
    fireEvent.change(screen.getByLabelText("Narrative"), { target: { value: "a seed" } });
    fireEvent.click(screen.getByRole("button", { name: /run radar/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/seed_text is required/i);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

describe("NarrativeOracle — brain unavailable (cmw-boss-facing-presentation, CRITICAL)", () => {
  it("shows the unified brain-unavailable banner instead of 'no voices available'", () => {
    render(<NarrativeOracle voices={[]} authorEmail="you@example.com" />);
    expect(screen.queryByText("no voices available")).not.toBeInTheDocument();
    const banner = screen.getByTestId("brain-unavailable-banner");
    expect(banner).toHaveTextContent("Brain unavailable");
    expect(banner).toHaveTextContent("the agents service or the Git brain may be unavailable");
    expect(screen.getByRole("link", { name: /brain setup docs/i })).toBeInTheDocument();
    // Run Radar is not runnable without a voice.
    expect(screen.getByRole("button", { name: /run radar/i })).toBeDisabled();
  });
});
