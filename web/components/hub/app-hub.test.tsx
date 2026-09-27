import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AppHub } from "@/components/hub/app-hub";

describe("AppHub", () => {
  it("shows a Newsroom card that links into the existing app", () => {
    render(<AppHub />);

    expect(screen.getByText("Newsroom")).toBeInTheDocument();
    const cta = screen.getByRole("link", { name: /open newsroom/i });
    expect(cta).toHaveAttribute("href", "/content-machine");
  });

  it("shows a non-functional 'more apps coming' affordance without inventing a fake app", () => {
    render(<AppHub />);

    expect(screen.getByText(/more apps coming soon/i)).toBeInTheDocument();
    // Only one real navigable app card exists — the coming-soon tile is not a link/button.
    expect(screen.getAllByRole("link")).toHaveLength(1);
  });
});
