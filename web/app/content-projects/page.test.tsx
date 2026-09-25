import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { DeskView } from "@/lib/content-workflow/types";

vi.mock("@/lib/session", () => ({
  requireUser: vi.fn().mockResolvedValue({ email: "captain@example.com", name: null, image: null }),
}));

vi.mock("@/lib/auth-actions", () => ({
  signInWithIdentity: vi.fn(),
  signInWithGoogle: vi.fn(),
  signOutAction: vi.fn(),
}));

const { fetchContentWorkflowDesk } = vi.hoisted(() => ({
  fetchContentWorkflowDesk: vi.fn(),
}));
vi.mock("@/lib/agents-client", () => ({ fetchContentWorkflowDesk }));

import ContentProjectsPage from "./page";

const desk: DeskView = {
  open_obligations: [],
  active_work: [
    {
      id: "project-123",
      version: 1,
      title: "Evidence that compounds",
      originating_idea_id: "idea-123",
      purpose_brief: {
        proposition: "Operational evidence should compound across a content family.",
        audience: "Enterprise AI leaders",
        angle: "Treat evidence as shared infrastructure.",
        desired_outcome: "Readers adopt an evidence-first production loop.",
        why_now: "AI content volume is rising faster than trust.",
        constraints: [],
      },
      authorities: [],
      default_voice_id: "demo-dana",
      evidence_base_id: "evidence-123",
      disposition: "active",
      suspension: "running",
      visibility: "visible",
      epoch: 1,
    },
  ],
  released_projects: [],
};

describe("ContentProjectsPage", () => {
  it("renders real active projects from the desk query with links to their studios", async () => {
    fetchContentWorkflowDesk.mockResolvedValue(desk);

    render(await ContentProjectsPage());

    expect(fetchContentWorkflowDesk).toHaveBeenCalledWith("captain@example.com");
    expect(screen.getByText("Evidence that compounds")).toBeInTheDocument();
    expect(
      screen.getByText("Operational evidence should compound across a content family."),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /evidence that compounds/i })).toHaveAttribute(
      "href",
      "/content-projects/project-123",
    );
  });
});
