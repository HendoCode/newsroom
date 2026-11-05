import { describe, expect, it, vi } from "vitest";

const { fetchContentWorkflowDesk, getCurrentUser } = vi.hoisted(() => ({
  fetchContentWorkflowDesk: vi.fn(),
  getCurrentUser: vi.fn(),
}));

vi.mock("@/lib/agents-client", () => ({
  AgentsRequestError: class extends Error {},
  fetchContentWorkflowDesk,
}));
vi.mock("@/lib/session", () => ({ getCurrentUser }));

import { GET } from "./route";

describe("content-workflow/desk BFF", () => {
  it("forwards the signed-in operator identity to the real desk query", async () => {
    getCurrentUser.mockResolvedValue({ email: "captain@example.com" });
    fetchContentWorkflowDesk.mockResolvedValue({
      open_obligations: [],
      active_work: [],
      released_projects: [],
    });

    const res = await GET();

    expect(fetchContentWorkflowDesk).toHaveBeenCalledWith("captain@example.com");
    expect(res.status).toBe(200);
  });
});
