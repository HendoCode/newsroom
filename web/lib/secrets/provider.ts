/**
 * The `SecretsProvider` seam (`web/`'s Node resolver): resolve a secret by name, just-in-time,
 * from whatever backend is configured (env / AWS / Azure — see `env-provider.ts`/
 * `aws-provider.ts`/`azure-provider.ts` and `factory.ts`). A thin resolver, not a framework: no
 * policy, no rotation scheduler, just a short in-memory cache per name with a force-refresh
 * escape hatch so a rotated secret is picked up without a rebuild/restart.
 *
 * Mirrors `agents/app/secrets/` (Python) — same backend names, same config env var names — so
 * both runtimes behave identically under the same deployment config.
 */

export class SecretNotFoundError extends Error {
  constructor(name: string) {
    super(`Secret not found: ${name}`);
    this.name = "SecretNotFoundError";
  }
}

export interface GetSecretOptions {
  forceRefresh?: boolean;
}

export interface SecretsProvider {
  /**
   * Return the current value of secret `name`. Cached for a short TTL after the first
   * successful read; pass `{ forceRefresh: true }` (or call `invalidate` first) to skip the
   * cache and re-read from the backend — the path a rotated secret needs, with no process
   * restart. Rejects with `SecretNotFoundError` if the backend has no value for `name`.
   */
  get(name: string, opts?: GetSecretOptions): Promise<string>;

  /** Drop the cached value for `name` (or every cached value when `name` is omitted) so the
   * next `get` call re-reads from the backend. */
  invalidate(name?: string): void;
}

interface CacheEntry {
  value: string;
  fetchedAtMs: number;
}

/**
 * Shared short-TTL in-memory cache every backend wraps its real fetch in. A cache hit within
 * `ttlSeconds` of the last successful fetch skips the backend call entirely.
 *
 * Subclasses implement `fetch` only — the actual per-backend read — and never call it directly;
 * always go through `get`.
 */
export abstract class CachingSecretsProvider implements SecretsProvider {
  private readonly cache = new Map<string, CacheEntry>();
  private readonly ttlMs: number;

  constructor(ttlSeconds = 300) {
    this.ttlMs = ttlSeconds * 1000;
  }

  async get(name: string, opts: GetSecretOptions = {}): Promise<string> {
    const now = Date.now();
    if (!opts.forceRefresh) {
      const cached = this.cache.get(name);
      if (cached && now - cached.fetchedAtMs < this.ttlMs) {
        return cached.value;
      }
    }
    const value = await this.fetch(name);
    this.cache.set(name, { value, fetchedAtMs: now });
    return value;
  }

  invalidate(name?: string): void {
    if (name === undefined) {
      this.cache.clear();
    } else {
      this.cache.delete(name);
    }
  }

  /** Backend-specific read. Reject with `SecretNotFoundError` if `name` is unset. */
  protected abstract fetch(name: string): Promise<string>;
}
