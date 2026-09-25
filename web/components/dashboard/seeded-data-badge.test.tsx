import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SeededDataBadge } from "@/components/dashboard/seeded-data-badge";

describe("SeededDataBadge — placeholder provenance with a how-to-make-it-real exit", () => {
  it("labels seeded data and links to /how-it-works", () => {
    render(<SeededDataBadge seeded />);
    expect(screen.getByTestId("seeded-data-badge")).toHaveTextContent("seeded data");
    expect(screen.getByRole("link", { name: /how do i make this real/i })).toHaveAttribute(
      "href",
      "/how-it-works",
    );
  });

  it("labels live data without the how-to link (nothing to make real)", () => {
    render(<SeededDataBadge seeded={false} />);
    expect(screen.getByTestId("seeded-data-badge")).toHaveTextContent("live data");
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("honors a surface-specific seeded tooltip", () => {
    render(<SeededDataBadge seeded seededTitle="Placeholder pool until a Radar run writes real spikes" />);
    expect(screen.getByTestId("seeded-data-badge")).toHaveAttribute(
      "title",
      "Placeholder pool until a Radar run writes real spikes",
    );
  });
});
