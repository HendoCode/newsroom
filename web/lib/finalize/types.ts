/**
 * Finalize/outputs domain types (cmw-ui-wireframes screen 10; D13/open-decisions Item 5).
 * Mirrors `Job.formats` (`agents/app/models/job.py`) 1:1 — `html`/`pdf`/`doc`.
 */

export type FinalizeFormat = "html" | "pdf" | "doc";

export interface FinalizeFormatOption {
  value: FinalizeFormat;
  label: string;
  description: string;
}

/** Canonical display order — also the order `normalizeFormats` restores regardless of toggle
 * order, so the request body and the outputs list stay in one stable sequence. */
export const FINALIZE_FORMAT_OPTIONS: readonly FinalizeFormatOption[] = [
  {
    value: "html",
    label: "Branded HTML",
    description:
      "Self-contained: semantic content injected into the versioned template, brand palette/fonts, logo inlined.",
  },
  {
    value: "pdf",
    label: "PDF",
    description:
      "Rendered from the branded HTML itself (headless Chromium) so HTML and PDF match exactly (D13).",
  },
  {
    value: "doc",
    label: "Clean Google Doc",
    description:
      "Semantic content pushed to Docs — styling stripped (Docs strips it anyway). Best for further editing.",
  },
];

export const DEFAULT_FINALIZE_FORMATS: readonly FinalizeFormat[] = ["html", "pdf", "doc"];
