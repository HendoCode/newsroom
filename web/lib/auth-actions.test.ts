import { beforeEach, describe, expect, it, vi } from "vitest";

// Mock NextAuth's signIn/signOut so the action wiring can be tested without a real session.
const signIn = vi.fn();
const signOut = vi.fn();
vi.mock("@/auth", () => ({
  signIn: (...args: unknown[]) => signIn(...args),
  signOut: (...args: unknown[]) => signOut(...args),
}));

import { signInWithGoogle, signInWithIdentity, signOutAction } from "@/lib/auth-actions";

beforeEach(() => {
  signIn.mockReset();
  signOut.mockReset();
});

describe("signInWithIdentity", () => {
  it("signs in as the declared identity — submitting an email signs you in as that user", async () => {
    const formData = new FormData();
    formData.set("email", "jane@example.com");
    formData.set("name", "Jane Doe");

    await signInWithIdentity("/pieces/123", formData);

    expect(signIn).toHaveBeenCalledWith("identity", {
      email: "jane@example.com",
      name: "Jane Doe",
      redirectTo: "/pieces/123",
    });
  });

  it("defaults a missing callbackUrl to /", async () => {
    const formData = new FormData();
    formData.set("email", "jane@example.com");

    await signInWithIdentity(undefined, formData);

    expect(signIn).toHaveBeenCalledWith(
      "identity",
      expect.objectContaining({ redirectTo: "/" }),
    );
  });

  it("coerces a missing display name to an empty string (no password/OAuth field involved)", async () => {
    const formData = new FormData();
    formData.set("email", "jane@example.com");

    await signInWithIdentity("/", formData);

    expect(signIn).toHaveBeenCalledWith("identity", expect.objectContaining({ name: "" }));
  });
});

describe("signInWithGoogle", () => {
  it("starts the Google OAuth round trip, returning to the callback URL", async () => {
    await signInWithGoogle("/pieces/123");
    expect(signIn).toHaveBeenCalledWith("google", { redirectTo: "/pieces/123" });
  });

  it("defaults a missing callbackUrl to /", async () => {
    await signInWithGoogle(undefined);
    expect(signIn).toHaveBeenCalledWith("google", { redirectTo: "/" });
  });
});

describe("signOutAction", () => {
  it("signs out and returns to the identity login screen", async () => {
    await signOutAction();
    expect(signOut).toHaveBeenCalledWith({ redirectTo: "/signin" });
  });
});
