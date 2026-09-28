import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { OperatorDesk } from "./operator-desk";

const pushMock = vi.fn();

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: pushMock }) }));

/**
 * Ground truth: `agents/app/content_workflow/models.py` enum *values* (kebab-case).
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

const BACKEND_OBLIGATION_KIND = {
  confirmInputSufficiency: "confirm-input-sufficiency",
  closeReview: "close-review",
  acceptFinalRevision: "accept-final-revision",
  authorizeRelease: "authorize-release",
  decideLesson: "decide-lesson",
  attentionRequired: "attention-required",
} as const;

/** A wire-shaped recent-pieces fixture — field set mirrors `agents/app/schemas.py`'s
 * `RecentPiece` (snake_case, naive-UTC timestamp strings), newest activity first as the
 * backend `/api/pieces/recent` returns it. */
const RECENT_PIECES = {
  source: "store",
  items: [
    {
      id: "piece-2",
      title: "Newer piece",
      slug: "newer-piece",
      stage: "review",
      voice: "demo-dana",
      owner: "test@example.com",
      created_at: "2026-08-30T06:00:00.000000",
      updated_at: "2026-08-31T06:00:00.000000",
      last_human_touch_at: null,
    },
    {
      id: "piece-1",
      title: null,
      slug: "untitled-piece",
      stage: "interviewing",
      voice: "demo-dana",
      owner: null,
      created_at: "2026-08-29T06:00:00.000000",
      updated_at: "2026-08-30T06:00:00.000000",
      last_human_touch_at: null,
    },
  ],
};

/** URL-dispatching fetch stub: the desk + recent-pieces mount-time fetches each get their own
 * shape, and submit still fails loudly on an unknown URL. */
function fetchStub(submitHandler?: (url: string, init?: RequestInit) => unknown) {
  return vi.fn().mockImplementation((url: string, init?: RequestInit) => {
    if (url === "/api/content-workflow/desk") {
      return Promise.resolve({
        ok: true,
        json: async () => ({ open_obligations: [], active_work: [], released_projects: [] }),
      });
    }
    if (url === "/api/pieces/recent") {
      return Promise.resolve({ ok: true, json: async () => RECENT_PIECES });
    }
    if (url === "/api/content-workflow/submit" && submitHandler) {
      return Promise.resolve(submitHandler(url, init));
    }
    throw new Error(`unexpected fetch ${url}`);
  });
}

beforeEach(() => {
  vi.stubGlobal("fetch", fetchStub());
});

afterEach(() => {
  vi.unstubAllGlobals();
  pushMock.mockClear();
});

describe("OperatorDesk", () => {
  it("renders Inbox/Machine/Library separation and first-mile form", async () => {
    render(<OperatorDesk email="test@example.com" />);
    expect(screen.getByText("Inbox — waiting on you")).toBeInTheDocument();
    expect(screen.getByText("Machine working")).toBeInTheDocument();
    expect(screen.getByText("Released projects")).toBeInTheDocument();
    expect(screen.getByText(/Start a project from this idea/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Run the Radar" })).toHaveAttribute(
      "href",
      "/narrative",
    );
    expect(screen.getByRole("link", { name: "Open the Vault" })).toHaveAttribute(
      "href",
      "/spikes",
    );
    await waitFor(() => expect(screen.getByText("Nothing needs you right now")).toBeInTheDocument());
  });

  it("fills the first-mile form and submits a backend-valid commit-idea command", async () => {
    const fetchMock = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (url === "/api/content-workflow/submit") {
          const body = JSON.parse(String(init?.body ?? "{}")) as { command_type?: string };
          if (!body.command_type || !BACKEND_COMMAND_KIND_VALUES.includes(body.command_type)) {
            return Promise.resolve({
              ok: false,
              status: 422,
              json: async () => ({
                error: `invalid command_type: ${body.command_type ?? "<missing>"}`,
              }),
            });
          }
          return Promise.resolve({
            ok: true,
            status: 200,
            json: async () => ({
              outcome: "applied",
              command_type: body.command_type,
              result_refs: { project_id: "proj-1", content_project_id: "proj-1" },
            }),
          });
        }
        if (url === "/api/content-workflow/desk") {
          return Promise.resolve({
            ok: true,
            json: async () => ({
              open_obligations: [
                {
                  id: "obl-1",
                  content_project_id: "proj-1",
                  kind: BACKEND_OBLIGATION_KIND.confirmInputSufficiency,
                  assignee: { email: "test@example.com" },
                  authority: "input-sufficiency",
                  subject: { kind: "content-project", id: "proj-1" },
                  state: "open",
                },
              ],
              active_work: [],
              released_projects: [],
            }),
          });
        }
        if (url === "/api/pieces/recent") {
          return Promise.resolve({ ok: true, json: async () => ({ source: "store", items: [] }) });
        }
        throw new Error(`unexpected fetch ${url}`);
      });
    vi.stubGlobal("fetch", fetchMock);

    render(<OperatorDesk email="test@example.com" />);

    await screen.findByText("Decide if there's enough to draft");

    fireEvent.change(screen.getByPlaceholderText("Idea title"), {
      target: { value: "Evidence that compounds" },
    });
    fireEvent.change(screen.getByPlaceholderText("Narrative / purpose"), {
      target: { value: "Operational evidence should compound across a content family." },
    });
    fireEvent.click(screen.getByRole("button", { name: /Start a project from this idea/ }));

    await waitFor(() => {
      expect(fetchMock.mock.calls.some((call) => call[0] === "/api/content-workflow/submit")).toBe(
        true,
      );
    });

    const submitCall = fetchMock.mock.calls.find(
      (call) => call[0] === "/api/content-workflow/submit",
    );
    if (!submitCall) throw new Error("submit was not called");
    const submitted = JSON.parse(String((submitCall[1] as RequestInit).body)) as {
      command_type: string;
      aggregate: { kind: string; id: string };
      actor: { subject_id?: string; email: string };
      payload: {
        type?: string;
        project_title: string;
        purpose_brief: { proposition: string };
        default_voice_id: string;
        anchor_title: string;
        anchor_slug: string;
        anchor_destination: string;
        authorities: Array<{ kind: string }>;
      };
      expected_version: number;
    };
    expect(submitted.command_type).toBe(BACKEND_COMMAND_KIND.commitIdea);
    expect(submitted.aggregate.kind).toBe("idea");
    expect(submitted.actor.email).toBe("test@example.com");
    expect(submitted.actor.subject_id).toBe("test@example.com");
    expect(submitted.payload.type).toBe(BACKEND_COMMAND_KIND.commitIdea);
    expect(submitted.payload.project_title).toBe("Evidence that compounds");
    expect(submitted.payload.purpose_brief.proposition).toBe(
      "Operational evidence should compound across a content family.",
    );
    expect(submitted.payload.default_voice_id).toBe("demo-dana");
    expect(submitted.payload.anchor_title).toBe("Evidence that compounds");
    expect(submitted.payload.anchor_slug).toBe("evidence-that-compounds");
    expect(submitted.payload.anchor_destination).toBe("blog");
    expect(submitted.payload.authorities.map((a) => a.kind)).toEqual([
      "direction",
      "input-sufficiency",
      "voice",
      "release",
    ]);
    expect(submitted.expected_version).toBe(0);

    expect(screen.queryByText(/invalid command_type|submit failed/i)).not.toBeInTheDocument();
    await waitFor(() => expect(pushMock).toHaveBeenCalled());
  });

  it("surfaces the recent-pieces strip from the live work-state (never a hardcoded list)", async () => {
    render(<OperatorDesk email="test@example.com" />);

    // Both pieces render in backend order (newest activity first), linking to piece-detail.
    const newer = await screen.findByRole("link", { name: "Newer piece" });
    expect(newer).toHaveAttribute("href", "/pieces/piece-2");
    const untitled = screen.getByRole("link", { name: "untitled-piece" }); // title falls back to slug
    expect(untitled).toHaveAttribute("href", "/pieces/piece-1");
    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent("Newer piece");
    expect(items[1]).toHaveTextContent("untitled-piece");
    // Stage + relative-time context ride along each row.
    expect(screen.getByText("Review")).toBeInTheDocument();
    expect(screen.getAllByText(/active .*ago|active just now/)).toHaveLength(2);
  });

  it("shows an honest empty state when the work-state has no pieces", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((url: string) => {
        if (url === "/api/content-workflow/desk") {
          return Promise.resolve({
            ok: true,
            json: async () => ({ open_obligations: [], active_work: [], released_projects: [] }),
          });
        }
        if (url === "/api/pieces/recent") {
          return Promise.resolve({ ok: true, json: async () => ({ source: "store", items: [] }) });
        }
        throw new Error(`unexpected fetch ${url}`);
      }),
    );

    render(<OperatorDesk email="test@example.com" />);

    expect(await screen.findByText(/No pieces yet/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "start from your own idea" })).toHaveAttribute(
      "href",
      "/pieces/new",
    );
  });

  it("degrades quietly when the recent-pieces endpoint is unreachable", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((url: string) => {
        if (url === "/api/content-workflow/desk") {
          return Promise.resolve({
            ok: true,
            json: async () => ({ open_obligations: [], active_work: [], released_projects: [] }),
          });
        }
        if (url === "/api/pieces/recent") {
          return Promise.resolve({ ok: false, status: 502, json: async () => ({}) });
        }
        throw new Error(`unexpected fetch ${url}`);
      }),
    );

    render(<OperatorDesk email="test@example.com" />);

    expect(
      await screen.findByText("Recent pieces are unavailable right now."),
    ).toBeInTheDocument();
    // The rest of the desk still renders — one projection failing never blanks the surface.
    expect(screen.getByText("Inbox — waiting on you")).toBeInTheDocument();
  });
});
