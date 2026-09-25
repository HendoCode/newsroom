import { describe, expect, it } from "vitest";

import { AzureSecretsProvider, type KeyVaultClientLike } from "@/lib/secrets/azure-provider";
import { SecretNotFoundError } from "@/lib/secrets/provider";

/** A fake Key Vault client — the DI seam means the real `@azure/identity`/
 * `@azure/keyvault-secrets` is never imported or called here; no real cloud calls happen in
 * this test. */
class FakeKeyVaultClient implements KeyVaultClientLike {
  calls: string[] = [];

  constructor(private values: Record<string, string>) {}

  async getSecret(name: string): Promise<string | undefined> {
    this.calls.push(name);
    return this.values[name];
  }
}

describe("AzureSecretsProvider", () => {
  it("fetches and normalizes underscores to hyphens", async () => {
    const client = new FakeKeyVaultClient({ "ANTHROPIC-API-KEY": "azure-secret-value" });
    const provider = new AzureSecretsProvider({ vaultUrl: "https://v.vault.azure.net/", client });
    await expect(provider.get("ANTHROPIC_API_KEY")).resolves.toBe("azure-secret-value");
    expect(client.calls).toEqual(["ANTHROPIC-API-KEY"]);
  });

  it("rejects with SecretNotFoundError when the secret is missing", async () => {
    const client = new FakeKeyVaultClient({});
    const provider = new AzureSecretsProvider({ vaultUrl: "https://v.vault.azure.net/", client });
    await expect(provider.get("MISSING")).rejects.toThrow(SecretNotFoundError);
  });

  it("caches so the client is called once", async () => {
    const client = new FakeKeyVaultClient({ "ANTHROPIC-API-KEY": "azure-secret-value" });
    const provider = new AzureSecretsProvider({
      vaultUrl: "https://v.vault.azure.net/",
      client,
      ttlSeconds: 300,
    });
    await provider.get("ANTHROPIC_API_KEY");
    await provider.get("ANTHROPIC_API_KEY");
    expect(client.calls).toEqual(["ANTHROPIC-API-KEY"]);
  });

  it("force refresh re-reads a rotated value", async () => {
    const values: Record<string, string> = { "ANTHROPIC-API-KEY": "first-value" };
    const client = new FakeKeyVaultClient(values);
    const provider = new AzureSecretsProvider({
      vaultUrl: "https://v.vault.azure.net/",
      client,
      ttlSeconds: 300,
    });
    await expect(provider.get("ANTHROPIC_API_KEY")).resolves.toBe("first-value");

    values["ANTHROPIC-API-KEY"] = "rotated-value";
    await expect(provider.get("ANTHROPIC_API_KEY")).resolves.toBe("first-value");
    await expect(provider.get("ANTHROPIC_API_KEY", { forceRefresh: true })).resolves.toBe(
      "rotated-value",
    );
  });
});
