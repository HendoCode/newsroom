import { describe, expect, it, vi } from "vitest";

const { fetchRecentPieces } = vi.hoisted(() => ({ fetchRecentPieces: vi.fn() }));

vi.mock("@/lib/agents-client", () => ({
  AgentsRequestError: class extends Error {},
  fetchRecentPieces,
}));

import { GET } from "./route";

describe("pieces/recent BFF", () => {
  it("proxies the agents recent-pieces projection verbatim", async () => {
    fetchRecentPieces.mockResolvedValue({
      source: "store",
      items: [
        {
          id: "p1",
          title: "A piece",
          slug: "a-piece",
          stage: "review",
          voice: "demo-dana",
          owner: null,
          created_at: "2026-08-31T00:00:00.000000",
          updated_at: "2026-08-31T06:00:00.000000",
          last_human_touch_at: null,
        },
      ],
    });

    const res = await GET();

    expect(fetchRecentPieces).toHaveBeenCalled();
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.source).toBe("store");
    expect(body.items).toHaveLength(1);
    expect(body.items[0].id).toBe("p1");
  });

  it("passes through the honest empty list (no seed fallback anywhere on this path)", async () => {
    fetchRecentPieces.mockResolvedValue({ source: "none", items: [] });

    const res = await GET();

    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ source: "none", items: [] });
  });

  it("degrades to 502 when the agents service is unreachable", async () => {
    fetchRecentPieces.mockRejectedValue(new Error("fetch failed"));

    const res = await GET();

    expect(res.status).toBe(502);
    expect((await res.json()).error).toBe("fetch failed");
  });
});
