/**
 * Backend selection: turns the `SECRETS_BACKEND` config env var into a concrete
 * `SecretsProvider`. Reads the same config env var names as `agents/app/secrets/` (Python) —
 * `SECRETS_BACKEND` / `SECRETS_CACHE_TTL_SECONDS` / `SECRETS_AWS_SSM_PREFIX` /
 * `SECRETS_AZURE_VAULT_URL` — so both runtimes behave identically under the same deployment
 * config. Left unset ("env", the default), `npm run dev` / `npm test` are unaffected by this
 * shim's existence.
 */

import { AwsSecretsProvider } from "./aws-provider";
import { AzureSecretsProvider } from "./azure-provider";
import { EnvSecretsProvider } from "./env-provider";
import type { GetSecretOptions, SecretsProvider } from "./provider";
import { SecretNotFoundError } from "./provider";

export { SecretNotFoundError };

const SUPPORTED_BACKENDS = ["env", "aws", "azure"] as const;

let cachedProvider: SecretsProvider | undefined;
let cachedKey: string | undefined;

function currentConfigKey(): string {
  return [
    process.env.SECRETS_BACKEND ?? "env",
    process.env.SECRETS_CACHE_TTL_SECONDS ?? "300",
    process.env.SECRETS_AWS_SSM_PREFIX ?? "/newsroom/",
    process.env.SECRETS_AZURE_VAULT_URL ?? "",
  ].join("|");
}

function buildProvider(): SecretsProvider {
  const backend = (process.env.SECRETS_BACKEND ?? "env").trim().toLowerCase();
  const ttlSeconds = Number(process.env.SECRETS_CACHE_TTL_SECONDS ?? "300");
  if (backend === "env") {
    return new EnvSecretsProvider(ttlSeconds);
  }
  if (backend === "aws") {
    return new AwsSecretsProvider({
      prefix: process.env.SECRETS_AWS_SSM_PREFIX ?? "/newsroom/",
      ttlSeconds,
    });
  }
  if (backend === "azure") {
    return new AzureSecretsProvider({
      vaultUrl: process.env.SECRETS_AZURE_VAULT_URL ?? "",
      ttlSeconds,
    });
  }
  throw new Error(
    `Unknown SECRETS_BACKEND "${backend}" (expected one of ${SUPPORTED_BACKENDS.join(", ")})`,
  );
}

/**
 * The process-wide `SecretsProvider` singleton — built once from current config and reused
 * (with its own in-memory secret cache) across calls. Rebuilt if `SECRETS_BACKEND`/etc. change
 * since the cached instance was built, mainly a test convenience since production config never
 * changes mid-process.
 */
export function getSecretsProvider(): SecretsProvider {
  const key = currentConfigKey();
  if (!cachedProvider || cachedKey !== key) {
    cachedProvider = buildProvider();
    cachedKey = key;
  }
  return cachedProvider;
}

/** Test seam: drop the cached provider (and its in-memory secret cache) so the next
 * `getSecretsProvider`/`getSecret` call rebuilds from current env. */
export function resetSecretsProvider(): void {
  cachedProvider = undefined;
  cachedKey = undefined;
}

/** Resolve secret `name` through the configured backend, returning `opts.default` (or `""`)
 * when it isn't set instead of throwing. */
export async function getSecret(
  name: string,
  opts: GetSecretOptions & { default?: string } = {},
): Promise<string> {
  try {
    return await getSecretsProvider().get(name, { forceRefresh: opts.forceRefresh });
  } catch (err) {
    if (err instanceof SecretNotFoundError) {
      return opts.default ?? "";
    }
    throw err;
  }
}
