/**
 * Pure helpers for the spike → kickoff hand-off (cmw-ui-wireframes screen 6), kept free of
 * React/fetch so they're trivially unit-tested.
 */

export function slugifyHeadline(headline: string): string {
  const slug = headline
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return slug || "spike";
}

/**
 * The agent's "fitting interviewer personas" pre-selection (screen 6 step 4). There is no
 * LLM-backed persona-recommender seam yet — building one would be new orchestration logic, out of
 * this ticket's scope (this screen only calls the existing interview-open endpoint). So this is a
 * deliberate, simple, fully-editable default: a small, generally-useful trio (specifics pressure /
 * unearned-claims pressure / a real account), intersected with whichever personas actually exist
 * in the brain so an unrecognized name is never pre-selected.
 */
const DEFAULT_PERSONA_PREFERENCE = ["ferriss", "skeptic", "customer"];

export function defaultInterviewerSelection(available: string[]): string[] {
  const known = new Set(available);
  const preferred = DEFAULT_PERSONA_PREFERENCE.filter((p) => known.has(p));
  return preferred.length > 0 ? preferred : available.slice(0, 3);
}
