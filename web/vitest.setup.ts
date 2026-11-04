import "@testing-library/jest-dom/vitest";
import { vi } from "vitest";

// next/font's real loaders (next/font/local for the app chrome's vendored fonts) run through
// Next's own build-time loader, which plain Vitest doesn't have. Mock to a stable, inert shape
// instead: callers only need back a `.variable`/`.className` string, echoing the requested
// `variable` name so tests can tell two distinct font loaders apart (see draft-view.test.tsx,
// which asserts the piece-detail preview's font variable is NOT the app chrome's
// `--font-serif`/`--font-sans`).
const mockFont = (opts?: { variable?: string }) => ({
  className: `mock-font${opts?.variable ?? ""}`,
  variable: `mock-var${opts?.variable ?? ""}`,
});
vi.mock("next/font/local", () => ({ default: mockFont }));

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
