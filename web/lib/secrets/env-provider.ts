/**
 * The `env` backend — process environment / a local `.env.local` loaded by Next.js. Zero cloud
 * deps; this is what an unset/"env" `SECRETS_BACKEND` resolves to, so local dev and tests are
 * unaffected by this shim's existence.
 */

import { CachingSecretsProvider, SecretNotFoundError } from "./provider";

export class EnvSecretsProvider extends CachingSecretsProvider {
  protected async fetch(name: string): Promise<string> {
    const value = process.env[name];
    if (value === undefined) {
      throw new SecretNotFoundError(name);
    }
    return value;
  }
}
