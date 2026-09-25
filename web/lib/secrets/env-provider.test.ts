import { afterEach, describe, expect, it, vi } from "vitest";

import { EnvSecretsProvider } from "@/lib/secrets/env-provider";
import { SecretNotFoundError } from "@/lib/secrets/provider";

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("EnvSecretsProvider", () => {
  it("resolves from process.env", async () => {
    vi.stubEnv("TEST_SECRET", "first-value");
    const provider = new EnvSecretsProvider();
    await expect(provider.get("TEST_SECRET")).resolves.toBe("first-value");
  });

  it("rejects with SecretNotFoundError when unset", async () => {
    const provider = new EnvSecretsProvider();
    await expect(provider.get("TEST_SECRET")).rejects.toThrow(SecretNotFoundError);
  });

  it("caches until force refresh", async () => {
    vi.stubEnv("TEST_SECRET", "first-value");
    const provider = new EnvSecretsProvider(300);
    await expect(provider.get("TEST_SECRET")).resolves.toBe("first-value");

    vi.stubEnv("TEST_SECRET", "rotated-value");
    await expect(provider.get("TEST_SECRET")).resolves.toBe("first-value");

    await expect(provider.get("TEST_SECRET", { forceRefresh: true })).resolves.toBe(
      "rotated-value",
    );
  });

  it("re-reads once the TTL expires without a force refresh", async () => {
    vi.stubEnv("TEST_SECRET", "first-value");
    const provider = new EnvSecretsProvider(0.05);
    await expect(provider.get("TEST_SECRET")).resolves.toBe("first-value");

    vi.stubEnv("TEST_SECRET", "rotated-value");
    await new Promise((resolve) => setTimeout(resolve, 100));
    await expect(provider.get("TEST_SECRET")).resolves.toBe("rotated-value");
  });

  it("invalidate(name) forces the next get() to re-read", async () => {
    vi.stubEnv("TEST_SECRET", "first-value");
    const provider = new EnvSecretsProvider(300);
    await provider.get("TEST_SECRET");

    vi.stubEnv("TEST_SECRET", "rotated-value");
    provider.invalidate("TEST_SECRET");
    await expect(provider.get("TEST_SECRET")).resolves.toBe("rotated-value");
  });

  it("invalidate() with no name drops every cached value", async () => {
    vi.stubEnv("TEST_SECRET", "first-value");
    const provider = new EnvSecretsProvider(300);
    await provider.get("TEST_SECRET");

    vi.stubEnv("TEST_SECRET", "rotated-value");
    provider.invalidate();
    await expect(provider.get("TEST_SECRET")).resolves.toBe("rotated-value");
  });
});
