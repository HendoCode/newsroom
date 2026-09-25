import "@testing-library/jest-dom/vitest";
import { vi } from "vitest";

// next/font/google's real implementation runs through Next's own build-time loader (which
// self-hosts the font and never touches the network at app runtime); calling it directly under
// plain Vitest has no such loader, so it would attempt a real network fetch. Mock it to a stable,
// inert shape instead — callers only need back a `.variable`/`.className` string, echoing the
// requested `variable` name so tests can tell two distinct font loaders apart (see
// draft-view.test.tsx, which asserts the piece-detail preview's font variable is NOT the app
// chrome's `--font-serif`/`--font-sans`).
vi.mock("next/font/google", () => {
  const font = (opts?: { variable?: string }) => ({
    className: `mock-font${opts?.variable ?? ""}`,
    variable: `mock-var${opts?.variable ?? ""}`,
  });
  return { Josefin_Sans: font, JetBrains_Mono: font };
});

// jsdom does not implement matchMedia; next-themes (enableSystem) calls it on mount.
// Minimal stub so components relying on it render under test.
if (!window.matchMedia) {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
}
