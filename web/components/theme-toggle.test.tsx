import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import RootLayout from "@/app/layout";
import { ThemeToggle } from "@/components/theme-toggle";

describe("ThemeToggle", () => {
  it("renders an accessible theme toggle inside the provider", () => {
    render(
      <RootLayout>
        <ThemeToggle />
      </RootLayout>,
    );
    // Radix gives the trigger button its a11y role/label for free.
    expect(screen.getByRole("button", { name: /toggle theme/i })).toBeInTheDocument();
  });
});

describe("theme default", () => {
  it("respects system dark preference on first load (no stored theme)", async () => {
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: query.includes("dark"),
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));
    // jsdom under this vitest may have no localStorage; next-themes reads/writes it
    const ls = { clear: vi.fn(), getItem: vi.fn(() => null), setItem: vi.fn(), removeItem: vi.fn() };
    Object.defineProperty(window, "localStorage", { value: ls, writable: true });
    render(
      <RootLayout>
        <div data-testid="child">ok</div>
      </RootLayout>,
    );
    await waitFor(() => {
      expect(document.documentElement.classList.contains("dark")).toBe(true);
    });
    expect(screen.getByTestId("child")).toBeInTheDocument();
  });
});
