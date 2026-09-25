/**
 * Pure format-selection helpers for the finalize/outputs screen (cmw-ui-wireframes screen 10).
 * Kept free of React/fetch so they're trivially unit-tested, mirroring `lib/sources/format.ts`.
 */

import { DEFAULT_FINALIZE_FORMATS, FINALIZE_FORMAT_OPTIONS, type FinalizeFormat } from "@/lib/finalize/types";

/** Toggle one format in/out of a selection, preserving no particular order (callers that need the
 * canonical order should run the result through `normalizeFormats`). */
export function toggleFormat(
  selected: readonly FinalizeFormat[],
  format: FinalizeFormat,
): FinalizeFormat[] {
  return selected.includes(format) ? selected.filter((f) => f !== format) : [...selected, format];
}

/** Restore the canonical html/pdf/doc order regardless of toggle order or duplicates. */
export function normalizeFormats(selected: readonly FinalizeFormat[]): FinalizeFormat[] {
  const set = new Set(selected);
  return FINALIZE_FORMAT_OPTIONS.map((o) => o.value).filter((f) => set.has(f));
}

/** At least one output format must be selected to finalize — a basic form-completeness gate, not
 * a §5 warn-not-block business rule (finalizing with zero formats would silently produce nothing,
 * per the finalize step's own "zero of requested formats is a real failure" contract). */
export function canFinalize(selected: readonly FinalizeFormat[]): boolean {
  return selected.length > 0;
}

/**
 * The `formats` value to send on the finalize request: `null` when every format is selected (the
 * finalize step's own default), otherwise the normalized subset (use case J "selectable at
 * finalize"). Assumes `canFinalize(selected)` — callers should not call this with an empty
 * selection.
 */
export function formatsForRequest(selected: readonly FinalizeFormat[]): FinalizeFormat[] | null {
  const normalized = normalizeFormats(selected);
  return normalized.length === DEFAULT_FINALIZE_FORMATS.length ? null : normalized;
}
