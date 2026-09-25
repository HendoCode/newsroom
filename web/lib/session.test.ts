import { beforeEach, describe, expect, it, vi } from "vitest";

// Mock the NextAuth `auth()` session reader and Next's `redirect()` so the accessor can be tested
// in isolation. `redirect` throws in real Next.js to halt rendering; we mirror that with a sentinel.
const auth = vi.fn();
vi.mock("@/auth", () => ({ auth: () => auth() }));

class RedirectError extends Error {
  constructor(public url: string) {
    super(`REDIRECT:${url}`);
  }
}
vi.mock("next/navigation", () => ({
  redirect: (url: string) => {
    throw new RedirectError(url);
  },
}));

import { getCurrentUser, requireUser } from "@/lib/session";

beforeEach(() => {
  auth.mockReset();
});

describe("getCurrentUser", () => {
  it("maps a session into the typed AppUser (email/name/image)", async () => {
    auth.mockResolvedValue({
      user: { email: "jane@example.com", name: "Jane Doe", image: "https://img/jane.png" },
    });
    await expect(getCurrentUser()).resolves.toEqual({
      email: "jane@example.com",
      name: "Jane Doe",
      image: "https://img/jane.png",
    });
  });

  it("defaults absent name/image to null", async () => {
    auth.mockResolvedValue({ user: { email: "jane@example.com" } });
    await expect(getCurrentUser()).resolves.toEqual({
      email: "jane@example.com",
      name: null,
      image: null,
    });
  });

  it("returns null when there is no session", async () => {
    auth.mockResolvedValue(null);
    await expect(getCurrentUser()).resolves.toBeNull();
  });

  it("returns null when the session has no email (not a usable identity)", async () => {
    auth.mockResolvedValue({ user: { name: "Nameless" } });
    await expect(getCurrentUser()).resolves.toBeNull();
  });
});

describe("requireUser", () => {
  it("returns the user when authenticated", async () => {
    auth.mockResolvedValue({ user: { email: "jane@example.com", name: "Jane" } });
    await expect(requireUser()).resolves.toEqual({
      email: "jane@example.com",
      name: "Jane",
      image: null,
    });
  });

  it("redirects to /signin when unauthenticated", async () => {
    auth.mockResolvedValue(null);
    await expect(requireUser()).rejects.toMatchObject({ url: "/signin" });
  });
});
