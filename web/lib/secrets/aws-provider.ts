/**
 * The `aws` backend — AWS Systems Manager Parameter Store, one parameter per secret name under a
 * shared prefix (default `/newsroom/`). Ambient IAM credentials only: an instance/task
 * role in production, the caller's SSO/OIDC session elsewhere — `@aws-sdk/client-ssm`'s default
 * credential provider chain resolves both, so no AWS key is ever stored here.
 *
 * `@aws-sdk/client-ssm` is loaded via a dynamic `import()` inside {@link RealSsmClient}, and only
 * when no `client` is injected — an `env`-backend deployment (the default) never loads it.
 */

import { CachingSecretsProvider, SecretNotFoundError } from "./provider";

/** The one operation this provider needs from an SSM client — small enough that tests can
 * implement a fake directly, with no dependency on the real SDK's types. */
export interface SsmClientLike {
  /** Resolve one parameter's value, or `undefined` if it doesn't exist. */
  getParameter(name: string): Promise<string | undefined>;
}

export interface AwsSecretsProviderOptions {
  prefix?: string;
  ttlSeconds?: number;
  /** Test seam: inject a fake client and the real SDK is never imported. */
  client?: SsmClientLike;
}

function isParameterNotFoundError(err: unknown): boolean {
  return (
    typeof err === "object" &&
    err !== null &&
    "name" in err &&
    (err as { name?: unknown }).name === "ParameterNotFound"
  );
}

class RealSsmClient implements SsmClientLike {
  async getParameter(name: string): Promise<string | undefined> {
    const { SSMClient, GetParameterCommand } = await import("@aws-sdk/client-ssm");
    const client = new SSMClient({});
    try {
      const response = await client.send(
        new GetParameterCommand({ Name: name, WithDecryption: true }),
      );
      return response.Parameter?.Value;
    } catch (err) {
      if (isParameterNotFoundError(err)) {
        return undefined;
      }
      throw err;
    }
  }
}

export class AwsSecretsProvider extends CachingSecretsProvider {
  private readonly prefix: string;
  private readonly client: SsmClientLike;

  constructor(opts: AwsSecretsProviderOptions = {}) {
    super(opts.ttlSeconds);
    this.prefix = opts.prefix ?? "/newsroom/";
    this.client = opts.client ?? new RealSsmClient();
  }

  protected async fetch(name: string): Promise<string> {
    const value = await this.client.getParameter(`${this.prefix}${name}`);
    if (value === undefined) {
      throw new SecretNotFoundError(name);
    }
    return value;
  }
}
