/**
 * Pre-finalize checks (cmw-ui-wireframes screen 10) — always WARN, never block (§5 flexibility
 * principle). Open GAPs/clearances are listed so the human sees what every output strips before
 * rendering, but nothing here disables the Finalize action.
 */

import type { PieceDetail } from "@/lib/pieces/types";

export interface PreFinalizeCheck {
  id: "open-gaps" | "open-clearances";
  severity: "warn" | "ok";
  message: string;
}

/** Always exactly [open-gaps check, open-clearances check] — a fixed tuple (not an open-ended
 * array) so callers can destructure without an `| undefined` from `noUncheckedIndexedAccess`. */
export function preFinalizeChecks(
  piece: Pick<PieceDetail, "open_gaps" | "open_clearances">,
): [PreFinalizeCheck, PreFinalizeCheck] {
  return [
    piece.open_gaps > 0
      ? {
          id: "open-gaps",
          severity: "warn",
          message: `${piece.open_gaps} open GAP${piece.open_gaps === 1 ? "" : "s"} in the editorial block — will be stripped from every output, but they're unresolved.`,
        }
      : { id: "open-gaps", severity: "ok", message: "0 open GAPs." },
    piece.open_clearances > 0
      ? {
          id: "open-clearances",
          severity: "warn",
          message: `${piece.open_clearances} open clearance${piece.open_clearances === 1 ? "" : "s"} — unresolved, but nothing here blocks finalizing (§5).`,
        }
      : { id: "open-clearances", severity: "ok", message: "0 open clearances." },
  ];
}

export function hasWarnings(checks: readonly PreFinalizeCheck[]): boolean {
  return checks.some((c) => c.severity === "warn");
}
