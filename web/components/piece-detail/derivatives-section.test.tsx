import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { DerivativesSection } from "@/components/piece-detail/derivatives-section";
import { COMMISSION_NOT_BUILT_REASON, DERIVATIVE_FORMATS } from "@/lib/pieces/derivatives";

describe("DerivativesSection", () => {
  it("shows existing and creatable groups, with every catalog format creatable when none exist", () => {
    render(<DerivativesSection />);

    expect(screen.getByRole("heading", { name: /existing/i })).toBeInTheDocument();
    expect(screen.getByText(/none commissioned yet/i)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /creatable/i })).toBeInTheDocument();

    for (const format of DERIVATIVE_FORMATS) {
      expect(screen.getByText(format.label)).toBeInTheDocument();
    }
    expect(screen.getAllByRole("button", { name: /commission/i })).toHaveLength(
      DERIVATIVE_FORMATS.length,
    );
  });

  it("lists a child native under Existing without a piece link, and offers Promote", () => {
    const onPromote = vi.fn();
    render(
      <DerivativesSection
        onPromote={onPromote}
        existing={[
          {
            id: "d1",
            title: "Token vs storage — LinkedIn",
            destination: "linkedin",
            lineage: "child",
          },
        ]}
      />,
    );

    expect(screen.getByText(/1 native/i)).toBeInTheDocument();
    expect(screen.getByText("Token vs storage — LinkedIn")).toBeInTheDocument();
    expect(screen.getByText("Child of this piece")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /linkedin post/i })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /promote linkedin post/i }));
    expect(onPromote).toHaveBeenCalledWith("d1");
    expect(screen.queryByRole("button", { name: /commission linkedin post/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /commission x thread/i })).toBeInTheDocument();
  });

  it("links a promoted native to its own piece", () => {
    render(
      <DerivativesSection
        existing={[
          {
            id: "d1",
            title: "Token vs storage — LinkedIn",
            destination: "linkedin",
            lineage: "promoted",
            promoted_piece_id: "piece-9",
            phase: "quality-closure",
          },
        ]}
      />,
    );

    expect(screen.getByText("Own piece")).toBeInTheDocument();
    expect(screen.getByText("In review")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /linkedin post/i })).toHaveAttribute(
      "href",
      "/pieces/piece-9",
    );
    expect(screen.queryByRole("button", { name: /promote/i })).not.toBeInTheDocument();
  });

  it("disables Commission with the honest not-built reason when no handler is wired", () => {
    render(<DerivativesSection />);
    const buttons = screen.getAllByRole("button", { name: /commission/i });
    for (const button of buttons) {
      expect(button).toBeDisabled();
      expect(button).toHaveAttribute("title", COMMISSION_NOT_BUILT_REASON);
    }
    expect(screen.getByText(COMMISSION_NOT_BUILT_REASON)).toBeInTheDocument();
  });

  it("enables Commission when onCommission is wired and records a child", () => {
    const onCommission = vi.fn();
    render(<DerivativesSection onCommission={onCommission} />);
    const button = screen.getByRole("button", { name: "Commission LinkedIn post" });
    expect(button).toBeEnabled();
    fireEvent.click(button);
    expect(onCommission).toHaveBeenCalledWith("linkedin-post");
  });

  it("frames publish as not the last beat and children as the default", () => {
    render(<DerivativesSection />);
    expect(screen.getByText(/publish is not the last beat/i)).toBeInTheDocument();
    expect(screen.getAllByText(/child of this piece/i).length).toBeGreaterThan(0);
  });
});

describe("DerivativesSection — derivative quality bar", () => {
  const clearedQuality = {
    required: true,
    cleared: true,
    bar: 9,
    aggregate: 9.2,
    council_revision: "rev-1",
    reasons: [],
    editors: ["slop-allergist", "voice-guardian", "technical-reviewer", "puri"],
    universal_gates: ["facts", "safety"] as ("facts" | "safety")[],
  };

  it("shows a cleared council badge with the aggregate for a publishable derivative", () => {
    render(
      <DerivativesSection
        existing={[
          {
            id: "d1",
            title: "Token vs storage — LinkedIn",
            destination: "linkedin",
            lineage: "promoted",
            promoted_piece_id: "piece-9",
            quality: clearedQuality,
          },
        ]}
      />,
    );

    expect(screen.getByText("Council 9.2/10")).toBeInTheDocument();
    expect(screen.queryByText(/council: not cleared/i)).not.toBeInTheDocument();
  });

  it("shows not-cleared with the blocking reason when the council is below the bar", () => {
    render(
      <DerivativesSection
        existing={[
          {
            id: "d1",
            title: "Token vs storage — LinkedIn",
            destination: "linkedin",
            lineage: "promoted",
            promoted_piece_id: "piece-9",
            quality: {
              ...clearedQuality,
              cleared: false,
              aggregate: 8.4,
              reasons: ["council aggregate 8.4/10 is below the 9 derivative bar"],
            },
          },
        ]}
      />,
    );

    expect(screen.getByText("Council: not cleared")).toBeInTheDocument();
    expect(screen.getByText(/below the 9 derivative bar/i)).toBeInTheDocument();
  });

  it("names the universal hard gates in a blocked reason", () => {
    render(
      <DerivativesSection
        existing={[
          {
            id: "d1",
            title: "Token vs storage — LinkedIn",
            destination: "linkedin",
            lineage: "promoted",
            promoted_piece_id: "piece-9",
            quality: {
              ...clearedQuality,
              cleared: false,
              reasons: ["universal hard gate failed: safety (slop-allergist applied a hard cap)"],
            },
          },
        ]}
      />,
    );

    expect(screen.getByText(/universal hard gate failed: safety/i)).toBeInTheDocument();
  });

  it("shows the destination council caption for creatable formats", () => {
    render(<DerivativesSection />);
    // LinkedIn post's destination judgment includes puri; universal gates always listed.
    expect(screen.getAllByText(/judges: .*puri/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/universal gates: facts, safety/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/own council ≥ 9\/10/i).length).toBeGreaterThan(0);
  });

  it("a child artifact shows not-cleared with the honest promote-first reason", () => {
    render(
      <DerivativesSection
        existing={[
          {
            id: "d1",
            title: "Token vs storage — LinkedIn",
            destination: "linkedin",
            lineage: "child",
            quality: {
              ...clearedQuality,
              cleared: false,
              aggregate: null,
              reasons: ["child artifact — promote it before it can clear its own council"],
            },
          },
        ]}
      />,
    );

    expect(screen.getByText("Council: not cleared")).toBeInTheDocument();
    expect(screen.getByText(/promote it before it can clear/i)).toBeInTheDocument();
  });
});
