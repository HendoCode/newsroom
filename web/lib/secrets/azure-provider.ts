/**
 * The `azure` backend — Azure Key Vault via `DefaultAzureCredential` (managed identity in
 * production; the developer's `az login`/env-based credential elsewhere) — no credential is ever
 * stored here, only the vault URL.
 *
 * Key Vault secret names may only contain alphanumerics and hyphens (no underscores), so a name
 * like `ANTHROPIC_API_KEY` is normalized to `ANTHROPIC-API-KEY` before the lookup.
 *
 * `@azure/identity`/`@azure/keyvault-secrets` are loaded via a dynamic `import()` inside
 * {@link RealKeyVaultClient}, and only when no `client` is injected — an `env`-backend
 * deployment (the default) never loads them.
 */

import { CachingSecretsProvider, SecretNotFoundError } from "./provider";

/** The one operation this provider needs from a Key Vault client — small enough that tests can
 * implement a fake directly, with no dependency on the real SDK's types. */
export interface KeyVaultClientLike {
  /** Resolve one secret's value, or `undefined` if it doesn't exist. */
  getSecret(name: string): Promise<string | undefined>;
}

export interface AzureSecretsProviderOptions {
  vaultUrl: string;
  ttlSeconds?: number;
  /** Test seam: inject a fake client and the real SDK is never imported. */
  client?: KeyVaultClientLike;
}

function isResourceNotFoundError(err: unknown): boolean {
  return (
    typeof err === "object" &&
    err !== null &&
    "statusCode" in err &&
    (err as { statusCode?: unknown }).statusCode === 404
  );
}

class RealKeyVaultClient implements KeyVaultClientLike {
  constructor(private readonly vaultUrl: string) {}

  async getSecret(name: string): Promise<string | undefined> {
    if (!this.vaultUrl) {
      throw new Error(
        "SECRETS_AZURE_VAULT_URL is not configured — required for SECRETS_BACKEND=azure",
      );
    }
    const { DefaultAzureCredential } = await import("@azure/identity");
    const { SecretClient } = await import("@azure/keyvault-secrets");
    const client = new SecretClient(this.vaultUrl, new DefaultAzureCredential());
    try {
      const secret = await client.getSecret(name);
      return secret.value;
    } catch (err) {
      if (isResourceNotFoundError(err)) {
        return undefined;
      }
      throw err;
    }
  }
}

export class AzureSecretsProvider extends CachingSecretsProvider {
  private readonly client: KeyVaultClientLike;

  constructor(opts: AzureSecretsProviderOptions) {
    super(opts.ttlSeconds);
    this.client = opts.client ?? new RealKeyVaultClient(opts.vaultUrl);
  }

  private static normalize(name: string): string {
    return name.replace(/_/g, "-");
  }

  protected async fetch(name: string): Promise<string> {
    const value = await this.client.getSecret(AzureSecretsProvider.normalize(name));
    if (value === undefined) {
      throw new SecretNotFoundError(name);
    }
    return value;
  }
}
