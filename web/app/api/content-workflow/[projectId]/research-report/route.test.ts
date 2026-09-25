import { afterEach, describe, expect, it, vi } from "vitest";

import { GET, POST } from "./route";

vi.mock("@/lib/agents-client", () => ({
  AgentsRequestError: class extends Error {},
}));

const params = { params: Promise.resolve({ projectId: "proj-1" }) };

afterEach(() => {
  vi.unstubAllGlobals();
  delete process.env.AGENTS_URL;
});

describe("content-workflow/[projectId]/research-report BFF", () => {
  it("GET proxies the research gate from agents", async () => {
    process.env.AGENTS_URL = "http://agents.test";
    const agentsFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ required: true, satisfied: false, satisfied_by: null, report: null, waiver: null }),
    });
    vi.stubGlobal("fetch", agentsFetch);

    const res = await GET(new Request("http://localhost/api/content-workflow/proj-1/research-report"), params);

    expect(agentsFetch).toHaveBeenCalledTimes(1);
    const [url, init] = agentsFetch.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://agents.test/api/content-workflow/proj-1/research-report");
    expect(init.method).toBe("GET");
    expect(res.status).toBe(200);
    const json = await res.json();
    expect(json.required).toBe(true);
    expect(json.satisfied).toBe(false);
  });

  it("POST forwards the report body verbatim and returns the agents status", async () => {
    process.env.AGENTS_URL = "http://agents.test";
    const reportBody = {
      subject: "Token vs storage economics",
      facts: [{ statement: "Inference grew 3x faster than training.", source: "Q4 2025 survey" }],
      opinions: [],
      open_questions: [],
      submitted_by: { subject_id: "test@example.com", email: "test@example.com" },
    };
    const agentsFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 201,
      json: async () => ({ id: "rep-1", content_project_id: "proj-1", status: "current", ...reportBody }),
    });
    vi.stubGlobal("fetch", agentsFetch);

    const res = await POST(
      new Request("http://localhost/api/content-workflow/proj-1/research-report", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(reportBody),
      }),
      params,
    );

    const [, init] = agentsFetch.mock.calls[0] as [string, RequestInit];
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual(reportBody);
    expect(res.status).toBe(201);
  });

  it("passes through the agents 422 for a report with no sourced facts", async () => {
    process.env.AGENTS_URL = "http://agents.test";
    const agentsFetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 422,
      json: async () => ({ detail: [{ msg: "a research report requires at least one sourced fact" }] }),
    });
    vi.stubGlobal("fetch", agentsFetch);

    const res = await POST(
      new Request("http://localhost/api/content-workflow/proj-1/research-report", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ subject: "s", facts: [], submitted_by: { email: "t@example.com" } }),
      }),
      params,
    );

    expect(res.status).toBe(422);
  });
});
