import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PipelineMiniRail } from "@/components/dashboard/pipeline-mini-rail";

describe("PipelineMiniRail — the dashboard card's compact echo of the Pipeline rail (decision C)", () => {
  it("renders nothing for a spike (no stage at all)", () => {
    const { container } = render(<PipelineMiniRail stage={null} round={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing for paused — off-rail, same as the main rail's own paused chip", () => {
    const { container } = render(<PipelineMiniRail stage="paused" round={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("is purely decorative — aria-hidden, since the adjacent StageBadge text carries the real state", () => {
    const { container } = render(<PipelineMiniRail stage="drafting" round={null} />);
    expect(container.querySelector('[aria-hidden="true"]')).toBeTruthy();
  });

  it("names the current cluster and the loop count once round > 1", () => {
    const { container } = render(<PipelineMiniRail stage="council" round={3} />);
    expect(container.querySelector("[title]")?.getAttribute("title")).toBe(
      "Pipeline: loop stage · loop 2×",
    );
  });

  it("omits the loop count at round 1 — hasn't actually looped yet", () => {
    const { container } = render(<PipelineMiniRail stage="review" round={1} />);
    expect(container.querySelector("[title]")?.getAttribute("title")).toBe("Pipeline: loop stage");
  });

  it("names the intake and ship clusters for their own stages", () => {
    const intake = render(<PipelineMiniRail stage="interviewing" round={null} />);
    expect(intake.container.querySelector("[title]")?.getAttribute("title")).toBe(
      "Pipeline: intake stage",
    );
    const ship = render(<PipelineMiniRail stage="published" round={null} />);
    expect(ship.container.querySelector("[title]")?.getAttribute("title")).toBe(
      "Pipeline: ship stage",
    );
  });
});
