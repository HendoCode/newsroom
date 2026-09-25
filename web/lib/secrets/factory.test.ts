import { afterEach, describe, expect, it, vi } from "vitest";

import { AwsSecretsProvider } from "@/lib/secrets/aws-provider";
import { AzureSecretsProvider } from "@/lib/secrets/azure-provider";
import { EnvSecretsProvider } from "@/lib/secrets/env-provider";
import { getSecret, getSecretsProvider, resetSecretsProvider } from "@/lib/secrets/factory";

afterEach(() => {
  vi.unstubAllEnvs();
  resetSecretsProvider();
});

describe("getSecretsProvider", () => {
  it("defaults to the env backend when SECRETS_BACKEND is unset", () => {
    expect(getSecretsProvider()).toBeInstanceOf(EnvSecretsProvider);
  });

  it("selects aws", () => {
    vi.stubEnv("SECRETS_BACKEND", "aws");
    expect(getSecretsProvider()).toBeInstanceOf(AwsSecretsProvider);
  });

  it("selects azure", () => {
    vi.stubEnv("SECRETS_BACKEND", "azure");
    vi.stubEnv("SECRETS_AZURE_VAULT_URL", "https://v.vault.azure.net/");
    expect(getSecretsProvider()).toBeInstanceOf(AzureSecretsProvider);
  });

  it("is case-insensitive", () => {
    vi.stubEnv("SECRETS_BACKEND", "ENV");
    expect(getSecretsProvider()).toBeInstanceOf(EnvSecretsProvider);
  });

  it("throws on an unknown backend", () => {
    vi.stubEnv("SECRETS_BACKEND", "gcp");
    expect(() => getSecretsProvider()).toThrow(/Unknown SECRETS_BACKEND/);
  });

  it("returns the same cached instance for unchanged config", () => {
    const a = getSecretsProvider();
    const b = getSecretsProvider();
    expect(a).toBe(b);
  });

  it("resetSecretsProvider drops the cached instance", () => {
    const a = getSecretsProvider();
    resetSecretsProvider();
    const b = getSecretsProvider();
    expect(a).not.toBe(b);
  });
});

describe("getSecret", () => {
  it("resolves a set value", async () => {
    vi.stubEnv("TEST_SECRET", "a-value");
    await expect(getSecret("TEST_SECRET")).resolves.toBe("a-value");
  });

  it("falls back to the provided default when unset", async () => {
    await expect(getSecret("TEST_SECRET_UNSET", { default: "fallback" })).resolves.toBe(
      "fallback",
    );
  });

  it("falls back to an empty string when unset and no default given", async () => {
    await expect(getSecret("TEST_SECRET_UNSET")).resolves.toBe("");
  });
});
