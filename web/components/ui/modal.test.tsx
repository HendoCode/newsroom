import * as React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Modal } from "@/components/ui/modal";

function ControlledModal({ initialOpen = true }: { initialOpen?: boolean }) {
  const [open, setOpen] = React.useState(initialOpen);
  return (
    <Modal open={open} onOpenChange={setOpen} title="Full draft" description="the whole thing">
      <p>the full long-form content</p>
    </Modal>
  );
}

describe("Modal", () => {
  it("renders nothing when closed", () => {
    render(
      <Modal open={false} onOpenChange={vi.fn()} title="Full draft">
        <p>hidden content</p>
      </Modal>,
    );
    expect(screen.queryByText("hidden content")).not.toBeInTheDocument();
  });

  it("renders its title, description, and children when open", () => {
    render(<ControlledModal />);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("Full draft")).toBeInTheDocument();
    expect(screen.getByText("the whole thing")).toBeInTheDocument();
    expect(screen.getByText("the full long-form content")).toBeInTheDocument();
  });

  it("closes on the close button, handing control back to the caller", () => {
    render(<ControlledModal />);
    fireEvent.click(screen.getByRole("button", { name: /close/i }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
