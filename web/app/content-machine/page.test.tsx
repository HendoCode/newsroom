import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/session", () => ({
  requireUser: vi.fn().mockResolvedValue({ email: "you@company", name: null, image: null }),
}));

vi.mock("@/lib/auth-actions", () => ({
  signInWithIdentity: vi.fn(),
  signInWithGoogle: vi.fn(),
  signOutAction: vi.fn(),
}));

const { fetchDashboard } = vi.hoisted(() => ({
  fetchDashboard: vi.fn(),
}));
vi.mock("@/lib/agents-client", () => ({ fetchDashboard }));

import ContentMachineHome from "./page";

describe("ContentMachineHome", () => {
  it("mounts the redesigned Dashboard (Inbox + Machine + Library), not the old Operator Desk", async () => {
    fetchDashboard.mockResolvedValue({ source: "store", items: [] });

    render(await ContentMachineHome());

    expect(fetchDashboard).toHaveBeenCalledWith("you@company");
    expect(screen.getByRole("heading", { name: "Dashboard" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Inbox" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /machine working/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Library" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Library" })).toHaveAttribute(
      "href",
      "/content-machine#library",
    );
    expect(screen.queryByText(/HumanObligation/i)).toBeNull();
    expect(screen.queryByText(/Operator Desk/i)).toBeNull();
  });
});
