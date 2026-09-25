import { describe, expect, it } from "vitest";

import type { CommandKind } from "./types";

/**
 * Compile-time canary locking `CommandKind` (in `./types.ts`) to the backend
 * `CommandKind` enum in `agents/app/content_workflow/models.py`.
 *
 * Ground truth is the backend enum's *values* (the kebab-case wire format), copied verbatim —
 * never read back from `./types.ts`, which is the file that drifted in PR #120.
 *
 * This is the enforcement the `cmw-fix-workflow-contract-drift` sharp edge (root AGENTS.md) said
 * was missing: "nothing currently enforces this contract stays in sync". A future change to
 * either enum that touches only one side fails `npm run typecheck` here — vitest alone does NOT
 * type-check, so the canary's value lives in `web/package.json`'s `typecheck` script.
 *
 * If this file fails to compile, do NOT edit the ground truth to match: reconcile the two enums
 * in the same commit per the established convention (see the `CommandKind` doc comment in
 * `./types.ts`).
 */
const BACKEND_COMMAND_KIND_VALUES = [
  "commit-idea",
  "declare-input-sufficient",
  "record-experiential-waiver",
  "commission-derivative",
  "accept-final-revision",
  "authorize-release",
  "record-trivial-edit-waiver",
  "record-quality-waiver",
] as const;

type BackendCommandValue = (typeof BACKEND_COMMAND_KIND_VALUES)[number];

/**
 * Bidirectional exhaustiveness, checked by `tsc`:
 * - The literal below must name every `CommandKind` member (missing key -> TS error) — so a
 *   backend value missing from the frontend union, or a frontend-only invention left in the
 *   union, both fail.
 * - Each key's value type is `true` only when that key is a real backend wire value
 *   (`never` otherwise), so a literal naming a key that isn't in the backend set fails.
 */
type CommandKindMirrorsBackend = {
  [K in CommandKind]: K extends BackendCommandValue ? true : never;
};

// eslint-disable-next-line @typescript-eslint/no-unused-vars
const _commandKindMirrorsBackend: CommandKindMirrorsBackend = {
  "commit-idea": true,
  "declare-input-sufficient": true,
  "record-experiential-waiver": true,
  "commission-derivative": true,
  "accept-final-revision": true,
  "authorize-release": true,
  "record-trivial-edit-waiver": true,
  "record-quality-waiver": true,
};

describe("CommandKind backend contract", () => {
  it("backend ground truth is the unique kebab-case wire values", () => {
    expect(new Set(BACKEND_COMMAND_KIND_VALUES).size).toBe(BACKEND_COMMAND_KIND_VALUES.length);
    expect(BACKEND_COMMAND_KIND_VALUES).toHaveLength(8);
    for (const value of BACKEND_COMMAND_KIND_VALUES) {
      expect(value).toMatch(/^[a-z]+(-[a-z]+)*$/);
    }
  });
});