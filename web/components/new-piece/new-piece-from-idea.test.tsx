import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { NewPieceFromIdea } from "@/components/new-piece/new-piece-from-idea";

const pushMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
}));

afterEach(() => {
  vi.unstubAllGlobals();
  pushMock.mockClear();
});

describe("NewPieceFromIdea — the narrative-first fast path (Option B, cmw-narrative-first-entry-point)", () => {
  it("mints a Narrative then a Spike (no Oracle run) and navigates straight to that spike's kickoff page", async () => {
    const fetchMock = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (url === "/api/narratives") {
        expect(JSON.parse(String(init?.body))).toEqual({
          seed_text: "Customers insulate themselves from data-centre risk.",
          audience: "infra leaders",
          angle: "multi-vendor resilience",
        });
        return Promise.resolve({ ok: true, json: async () => ({ id: "narrative-1" }) });
      }
      if (url === "/api/spikes/from-narrative") {
        expect(JSON.parse(String(init?.body))).toEqual({
          narrative_id: "narrative-1",
          headline: "Why single-vendor infra is a hidden risk",
        });
        return Promise.resolve({ ok: true, json: async () => ({ id: "spike-1" }) });
      }
      throw new Error(`unexpected fetch ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<NewPieceFromIdea voices={["demo-mira", "demo-dana"]} authorEmail="you@example.com" />);

    fireEvent.change(screen.getByLabelText("Working title"), {
      target: { value: "Why single-vendor infra is a hidden risk" },
    });
    fireEvent.change(screen.getByLabelText("Your narrative"), {
      target: { value: "Customers insulate themselves from data-centre risk." },
    });
    fireEvent.change(screen.getByLabelText("Audience"), { target: { value: "infra leaders" } });
    fireEvent.change(screen.getByLabelText("Angle intent"), {
      target: { value: "multi-vendor resilience" },
    });

    fireEvent.click(screen.getByRole("button", { name: /start piece/i }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/spikes/spike-1?voice=demo-mira"));
  });

  it("disables submit until a working title and a narrative are both entered", () => {
    render(<NewPieceFromIdea voices={["demo-mira"]} authorEmail="you@example.com" />);

    expect(screen.getByRole("button", { name: /start piece/i })).toBeDisabled();

    fireEvent.change(screen.getByLabelText("Working title"), { target: { value: "A title" } });
    expect(screen.getByRole("button", { name: /start piece/i })).toBeDisabled();

    fireEvent.change(screen.getByLabelText("Your narrative"), { target: { value: "A narrative" } });
    expect(screen.getByRole("button", { name: /start piece/i })).toBeEnabled();
  });

  it("shows an inline error when minting the narrative fails and never mints a spike", async () => {
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url === "/api/narratives") {
        return Promise.resolve({ ok: false, json: async () => ({ error: "seed_text is required" }) });
      }
      throw new Error(`unexpected fetch ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<NewPieceFromIdea voices={["demo-mira"]} authorEmail="you@example.com" />);
    fireEvent.change(screen.getByLabelText("Working title"), { target: { value: "A title" } });
    fireEvent.change(screen.getByLabelText("Your narrative"), { target: { value: "A narrative" } });
    fireEvent.click(screen.getByRole("button", { name: /start piece/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/seed_text is required/i);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(pushMock).not.toHaveBeenCalled();
  });

  it("shows an inline error when minting the spike fails and never navigates away", async () => {
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url === "/api/narratives") {
        return Promise.resolve({ ok: true, json: async () => ({ id: "narrative-1" }) });
      }
      if (url === "/api/spikes/from-narrative") {
        return Promise.resolve({ ok: false, json: async () => ({ error: "could not start the piece" }) });
      }
      throw new Error(`unexpected fetch ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<NewPieceFromIdea voices={["demo-mira"]} authorEmail="you@example.com" />);
    fireEvent.change(screen.getByLabelText("Working title"), { target: { value: "A title" } });
    fireEvent.change(screen.getByLabelText("Your narrative"), { target: { value: "A narrative" } });
    fireEvent.click(screen.getByRole("button", { name: /start piece/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/could not start the piece/i);
    expect(pushMock).not.toHaveBeenCalled();
  });
});
