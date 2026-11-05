import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PreFinalizeChecks } from "@/components/finalize/pre-finalize-checks";

describe("PreFinalizeChecks", () => {
  it("shows a clean state with 0 open GAPs/clearances and never disables anything", () => {
    render(<PreFinalizeChecks piece={{ open_gaps: 0, open_clearances: 0 }} />);
    expect(screen.getByText(/0 open GAPs\./)).toBeInTheDocument();
    expect(screen.getByText(/0 open clearances\./)).toBeInTheDocument();
    expect(screen.getByText(/you can finalize anyway/i)).toBeInTheDocument();
  });

  it("warns on open GAPs/clearances but always says finalize proceeds anyway (§5)", () => {
    render(<PreFinalizeChecks piece={{ open_gaps: 2, open_clearances: 1 }} />);
    expect(screen.getByText(/2 open GAPs in the editorial block/i)).toBeInTheDocument();
    expect(screen.getByText(/1 open clearance —/i)).toBeInTheDocument();
    expect(screen.getByText(/you can finalize anyway/i)).toBeInTheDocument();
  });
});
