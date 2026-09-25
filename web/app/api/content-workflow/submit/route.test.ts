import { afterEach, describe, expect, it, vi } from "vitest";

import { POST } from "./route";

vi.mock("@/lib/agents-client", () => ({
  AgentsRequestError: class extends Error {},
}));

/**
 * Ground truth: `agents/app/content_workflow/models.py` `CommandKind` *values*.
 * Do not read these from `web/lib/content-workflow/types.ts` — that file is the
 * thing that drifted.
 */
const BACKEND_COMMAND_KIND = {
  commitIdea: "commit-idea",
  declareInputSufficient: "declare-input-sufficient",
  recordExperientialWaiver: "record-experiential-waiver",
  commissionDerivative: "commission-derivative",
  acceptFinalRevision: "accept-final-revision",
  authorizeRelease: "authorize-release",
  recordTrivialEditWaiver: "record-trivial-edit-waiver",
} as const;

const BACKEND_COMMAND_KIND_VALUES: readonly string[] = Object.values(BACKEND_COMMAND_KIND);

/**
 * Verbatim JSON body `OperatorDesk.handleCommitIdea` currently constructs and POSTs
 * (`web/app/content-machine/operator-desk.tsx`). Field names, nesting, and the
 * `command_type` string are copied from the component, not guessed.
 */
function operatorDeskSubmitBody(email: string) {
  const actor = { subject_id: email, email, display_name: email };
  return {
    schema_version: 1,
    command_type: "commit-idea",
    aggregate: { kind: "idea", id: "idea-1" },
    actor,
    idempotency_key: "idea-1",
    expected_version: 0,
    payload: {
      type: "commit-idea",
      project_title: "Evidence that compounds",
      purpose_brief: {
        proposition: "Operational evidence should compound across a content family.",
        audience: "General",
        angle: "Default",
        desired_outcome: "Audience adopts core proposition",
        why_now: "Relevant operational need",
        constraints: [],
      },
      default_voice_id: "demo-dana",
      authorities: [
        { kind: "direction", assignee: actor, scope: "project" },
        { kind: "input-sufficiency", assignee: actor, scope: "project" },
        { kind: "voice", assignee: actor, scope: "project" },
        { kind: "release", assignee: actor, scope: "project" },
      ],
      anchor_title: "Evidence that compounds",
      anchor_slug: "evidence-that-compounds",
      anchor_destination: "blog",
    },
  };
}

function mockAgentsValidatingCommandKind() {
  return vi.fn().mockImplementation(async (_url: string, init?: RequestInit) => {
    const body = JSON.parse(String(init?.body ?? "{}")) as { command_type?: string };
    if (!body.command_type || !BACKEND_COMMAND_KIND_VALUES.includes(body.command_type)) {
      return {
        ok: false,
        status: 422,
        json: async () => ({
          detail: [
            {
              type: "enum",
              loc: ["body", "command_type"],
              msg: `Input should be ${BACKEND_COMMAND_KIND_VALUES.map((v) => `'${v}'`).join(", ")}`,
              input: body.command_type,
            },
          ],
        }),
      };
    }
    return {
      ok: true,
      status: 200,
      json: async () => ({
        outcome: "applied",
        command_type: body.command_type,
        result_refs: { project_id: "proj-1", content_project_id: "proj-1" },
      }),
    };
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
  delete process.env.AGENTS_URL;
});

describe("content-workflow/submit BFF", () => {
  it("round-trips the OperatorDesk submit payload to a contract-checking agents backend", async () => {
    process.env.AGENTS_URL = "http://agents.test";
    const agentsFetch = mockAgentsValidatingCommandKind();
    vi.stubGlobal("fetch", agentsFetch);

    const deskBody = operatorDeskSubmitBody("test@example.com");
    const res = await POST(
      new Request("http://localhost/api/content-workflow/submit", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(deskBody),
      }),
    );

    expect(agentsFetch).toHaveBeenCalledTimes(1);
    const [url, init] = agentsFetch.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://agents.test/api/content-workflow/submit");
    expect(init.method).toBe("POST");
    const forwarded = JSON.parse(String(init.body)) as { command_type: string };
    // Backend CommandKind.commit_idea.value == "commit-idea". OperatorDesk must send
    // that wire value (not the Python member name "commit_idea").
    expect(forwarded.command_type).toBe(BACKEND_COMMAND_KIND.commitIdea);
    expect(res.status).toBe(200);
    const json = await res.json();
    expect(json.outcome).toBe("applied");
  });
});
