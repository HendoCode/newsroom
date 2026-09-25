import { describe, expect, it } from "vitest";

import { AwsSecretsProvider, type SsmClientLike } from "@/lib/secrets/aws-provider";
import { SecretNotFoundError } from "@/lib/secrets/provider";

/** A fake SSM client — the DI seam means the real `@aws-sdk/client-ssm` is never imported or
 * called here; no real cloud calls happen in this test. */
class FakeSsmClient implements SsmClientLike {
  calls: string[] = [];

  constructor(private values: Record<string, string>) {}

  async getParameter(name: string): Promise<string | undefined> {
    this.calls.push(name);
    return this.values[name];
  }
}

describe("AwsSecretsProvider", () => {
  it("fetches by prefixed parameter name", async () => {
    const client = new FakeSsmClient({ "/content-machine/ANTHROPIC_API_KEY": "aws-secret-value" });
    const provider = new AwsSecretsProvider({ prefix: "/content-machine/", client });
    await expect(provider.get("ANTHROPIC_API_KEY")).resolves.toBe("aws-secret-value");
    expect(client.calls).toEqual(["/content-machine/ANTHROPIC_API_KEY"]);
  });

  it("rejects with SecretNotFoundError when the parameter is missing", async () => {
    const client = new FakeSsmClient({});
    const provider = new AwsSecretsProvider({ prefix: "/content-machine/", client });
    await expect(provider.get("MISSING")).rejects.toThrow(SecretNotFoundError);
  });

  it("caches so the client is called once", async () => {
    const client = new FakeSsmClient({ "/content-machine/ANTHROPIC_API_KEY": "aws-secret-value" });
    const provider = new AwsSecretsProvider({ prefix: "/content-machine/", client, ttlSeconds: 300 });
    await provider.get("ANTHROPIC_API_KEY");
    await provider.get("ANTHROPIC_API_KEY");
    expect(client.calls).toEqual(["/content-machine/ANTHROPIC_API_KEY"]);
  });

  it("force refresh re-reads a rotated value", async () => {
    const values: Record<string, string> = { "/content-machine/ANTHROPIC_API_KEY": "first-value" };
    const client = new FakeSsmClient(values);
    const provider = new AwsSecretsProvider({ prefix: "/content-machine/", client, ttlSeconds: 300 });
    await expect(provider.get("ANTHROPIC_API_KEY")).resolves.toBe("first-value");

    values["/content-machine/ANTHROPIC_API_KEY"] = "rotated-value";
    await expect(provider.get("ANTHROPIC_API_KEY")).resolves.toBe("first-value");
    await expect(provider.get("ANTHROPIC_API_KEY", { forceRefresh: true })).resolves.toBe(
      "rotated-value",
    );
  });
});
