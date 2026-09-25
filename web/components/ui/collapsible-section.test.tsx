import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CollapsibleSection } from "@/components/ui/collapsible-section";

describe("CollapsibleSection", () => {
  it("hides its children by default and reveals them on toggle", () => {
    render(
      <CollapsibleSection title="Council record" summary="aggregate 8.0">
        <p>the full breakdown</p>
      </CollapsibleSection>,
    );
    expect(screen.getByText("aggregate 8.0")).toBeInTheDocument();
    expect(screen.queryByText("the full breakdown")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /show more details.*council record/i }));
    expect(screen.getByText("the full breakdown")).toBeInTheDocument();
  });

  it("starts open when defaultExpanded is set", () => {
    render(
      <CollapsibleSection title="Current revision" defaultExpanded>
        <p>a short tweet-sized draft</p>
      </CollapsibleSection>,
    );
    expect(screen.getByText("a short tweet-sized draft")).toBeInTheDocument();
  });

  it("renders children directly with no toggle when empty", () => {
    render(
      <CollapsibleSection title="Council record" empty>
        <p>No council pass yet.</p>
      </CollapsibleSection>,
    );
    expect(screen.getByText("No council pass yet.")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("keeps pinned content visible regardless of collapse state", () => {
    render(
      <CollapsibleSection title="Interview transcript" pinned={<button>Resume interview</button>}>
        <p>every turn</p>
      </CollapsibleSection>,
    );
    expect(screen.getByRole("button", { name: "Resume interview" })).toBeInTheDocument();
    expect(screen.queryByText("every turn")).not.toBeInTheDocument();
  });
});
