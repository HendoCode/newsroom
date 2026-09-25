import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  BRAIN_SETUP_DOCS_HREF,
  BrainUnavailableBanner,
} from "@/components/brain/brain-unavailable-banner";

describe("BrainUnavailableBanner — the unified brain-down message (cmw-boss-facing-presentation)", () => {
  it("names the shared root cause with the voice-kit's canonical phrasing", () => {
    render(<BrainUnavailableBanner />);
    expect(screen.getByRole("alert")).toHaveTextContent("Brain unavailable");
    expect(screen.getByRole("alert")).toHaveTextContent(
      "the agents service or the Git brain may be unavailable",
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Try again shortly");
  });

  it("carries the subject a caller names without forking the root-cause sentence", () => {
    render(<BrainUnavailableBanner subject="The voice list" />);
    expect(screen.getByRole("alert")).toHaveTextContent("The voice list can’t be reached");
    expect(screen.getByRole("alert")).toHaveTextContent(
      "the agents service or the Git brain may be unavailable",
    );
  });

  it("links to the brain setup docs", () => {
    render(<BrainUnavailableBanner />);
    const link = screen.getByRole("link", { name: /brain setup docs/i });
    expect(link).toHaveAttribute("href", BRAIN_SETUP_DOCS_HREF);
  });
});
