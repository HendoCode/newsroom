import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ReleaseGateView } from "@/lib/content-workflow/types";

import { ReleaseSection } from "./release-section";

function gate(overrides: Partial<ReleaseGateView> = {}): ReleaseGateView {
  return {
    piece_id: "piece-1",
    accepted_revision: null,
    current_revision: null,
    approval_valid: false,
    invalidated: false,
    waiver_reason: null,
    releases: [],
    authorize_enabled: false,
    reason: "No quality-cleared revision has been accepted yet.",
    ...overrides,
  };
}

function renderSection(overrides: Partial<ReleaseGateView> = {}, onChanged = vi.fn()) {
  return render(
    <ReleaseSection
      projectId="proj-1"
      release={gate(overrides)}
      projectVersion={3}
      email="operator@example.com"
      onChanged={onChanged}
    />,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ReleaseSection", () => {
  it("keeps Authorize release disabled until an accepted candidate exists", () => {
    renderSection();
    expect(screen.getByRole("button", { name: /^authorize release$/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /accept final revision/i })).toBeInTheDocument();
  });

  it("lists existing immutable numbered releases and offers another authorization", () => {
    renderSection({
      approval_valid: true,
      authorize_enabled: true,
      reason: "The accepted revision matches the current canonical content.",
      releases: [
        {
          piece_id: "piece-1",
          release_number: 1,
          revision: "abc12345ffff",
          authorized_by_subject_id: "operator@example.com",
          authorized_at: "2026-08-31T06:00:00.000000",
          html_url: "https://example/1/branded.html",
        },
      ],
    });
    expect(screen.getByText(/Release 1/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /authorize another release/i })).toBeEnabled();
  });

  it("posts authorize-release through the existing submit BFF, never a local transition", async () => {
    const onChanged = vi.fn();
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ outcome: "applied" }),
    });
    vi.stubGlobal("fetch", fetchMock);
    renderSection(
      {
        approval_valid: true,
        authorize_enabled: true,
        reason: "ready",
      },
      onChanged,
    );
    fireEvent.click(screen.getByRole("button", { name: /^authorize release$/i }));
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/content-workflow/submit",
      expect.objectContaining({ method: "POST" }),
    );
    const firstCall = fetchMock.mock.calls[0];
    expect(firstCall).toBeDefined();
    const body = JSON.parse((firstCall?.[1] as { body: string }).body);
    expect(body.command_type).toBe("authorize-release");
    expect(body.payload.type).toBe("authorize-release");
    expect(body.payload.piece_id).toBe("piece-1");
  });

  it("an invalidated approval offers the recorded trivial-edit waiver path", async () => {
    const onChanged = vi.fn();
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ outcome: "applied" }),
    });
    vi.stubGlobal("fetch", fetchMock);
    renderSection(
      {
        approval_valid: false,
        invalidated: true,
        authorize_enabled: false,
        accepted_revision: "aaa",
        current_revision: "bbb",
        reason: "Canonical content changed since approval.",
      },
      onChanged,
    );
    expect(screen.getByRole("button", { name: /^authorize release$/i })).toBeDisabled();
    fireEvent.change(screen.getByLabelText(/why is this edit trivial/i), {
      target: { value: "Fixed a typo in the heading." },
    });
    fireEvent.click(screen.getByRole("button", { name: /record waiver/i }));
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    const firstCall = fetchMock.mock.calls[0];
    expect(firstCall).toBeDefined();
    const body = JSON.parse((firstCall?.[1] as { body: string }).body);
    expect(body.command_type).toBe("record-trivial-edit-waiver");
    expect(body.payload.from_revision).toBe("aaa");
    expect(body.payload.to_revision).toBe("bbb");
    expect(body.payload.reason).toBe("Fixed a typo in the heading.");
  });
});
