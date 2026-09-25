import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ProjectWorkspaceView } from "@/lib/content-workflow/types";

import { PieceStudio } from "./piece-studio";

function view(overrides: Partial<ProjectWorkspaceView> = {}): ProjectWorkspaceView {
  return {
    schema_version: 1,
    generated_at: "2026-08-31T00:00:00.000Z",
    project: {
      id: "proj1",
      version: 1,
      title: "Token vs storage",
      originating_idea_id: "idea-1",
      purpose_brief: {
        proposition: "customers insulating from data-centre risk",
        audience: "General",
        angle: "Default",
        desired_outcome: "adopt",
        why_now: "now",
        constraints: [],
      },
      authorities: [],
      default_voice_id: "demo-dana",
      evidence_base_id: "eb1",
      disposition: "active",
      suspension: "running",
      visibility: "visible",
      epoch: 1,
    },
    derived_phase: "producing",
    phase_reason: "in flight",
    available_commands: [],
    open_obligations: [],
    piece_family: [],
    artifact_readiness: {},
    active_work: [],
    consistency_warnings: [],
    ...overrides,
  };
}

describe("PieceStudio", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => [] }));
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows explicit error when fetchError present", () => {
    render(
      <PieceStudio
        projectId="p1"
        initialView={null}
        fetchError="Couldn't load this project right now."
        email="t@example.com"
      />,
    );
    expect(screen.getByText(/Couldn't load this project right now/)).toBeInTheDocument();
  });

  it("renders honest empty placeholders when no view", () => {
    render(<PieceStudio projectId="p1" initialView={null} fetchError={null} email="t@example.com" />);
    expect(screen.getByText("No purpose written yet.")).toBeInTheDocument();
  });

  it("does not draw the Derivatives catalog before the project has shipped", () => {
    render(<PieceStudio projectId="proj1" initialView={view()} fetchError={null} email="t@example.com" />);
    expect(screen.queryByText(/publish is not the last beat/i)).not.toBeInTheDocument();
  });

  it("post-publish, shows existing family derivatives and the creatable catalog", () => {
    render(
      <PieceStudio
        projectId="proj1"
        fetchError={null}
        email="t@example.com"
        initialView={view({
          derived_phase: "completed",
          piece_family: [
            {
              id: "anchor-1",
              version: 1,
              role: "anchor",
              title: "Token vs storage",
              destination: "blog",
              voice_id: "demo-dana",
              disposition: "completed",
              suspension: "running",
              visibility: "visible",
              derived_phase: "released",
              phase_reason: "shipped",
              artifact_readiness: {},
              active_work: [],
            },
            {
              id: "deriv-1",
              version: 1,
              role: "derivative",
              title: "Token vs storage — LinkedIn",
              destination: "linkedin",
              voice_id: "demo-dana",
              disposition: "active",
              suspension: "running",
              visibility: "visible",
              derived_phase: "quality-closure",
              phase_reason: "in council",
              source_anchor_revision_id: "rev-1",
              artifact_readiness: {},
              active_work: [],
            },
          ],
        })}
      />,
    );
    expect(screen.getByText(/publish is not the last beat/i)).toBeInTheDocument();
    expect(screen.getAllByText(/Token vs storage — LinkedIn/).length).toBeGreaterThan(0);
    expect(screen.getByText("Child of this piece")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /commission newsletter/i })).toBeEnabled();
  });

  it("surfaces the research requirement when the backend projects one", () => {
    render(
      <PieceStudio
        projectId="proj1"
        fetchError={null}
        email="t@example.com"
        initialView={view({
          research: {
            required: true,
            satisfied: false,
            satisfied_by: null,
            report: null,
            waiver: null,
          },
        })}
      />,
    );
    expect(screen.getByText("Research")).toBeInTheDocument();
    expect(
      screen.getByText(/A sourced research report is required before interviews can open/i),
    ).toBeInTheDocument();
  });
});
