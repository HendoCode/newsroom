/**
 * Splits a semantic `draft.html` document (domain model §1.10/§1.11) into the publishable body and
 * its trailing `<section class="editorial">` block — the thing external-share (D11) and finalize
 * (D13) both strip via one shared routine, and the thing this screen shows as a visible, labeled
 * sub-section (cmw-ui-wireframes screen 2 UX decision #3) rather than hiding it inside the raw doc.
 *
 * `draft.html` is a full, self-contained document (`<html><body>…</body></html>`); regex extraction
 * (not a DOM parser) keeps this usable on both the server and the client with no new dependency —
 * the shape is simple and stable (one document, one trailing editorial section).
 */

export interface ParsedDraft {
  /** The document body with the editorial section removed — the publishable content. */
  bodyHtml: string;
  /** The editorial block's inner HTML (GAP/NOTE/CLEARANCE annotations), or `null` if absent. */
  editorialHtml: string | null;
}

const BODY_RE = /<body[^>]*>([\s\S]*)<\/body>/i;
const EDITORIAL_SECTION_RE =
  /<section[^>]*\bclass="[^"]*\beditorial\b[^"]*"[^>]*>([\s\S]*?)<\/section>/i;

export function parseDraftHtml(draftHtml: string): ParsedDraft {
  const bodyMatch = BODY_RE.exec(draftHtml);
  const body = bodyMatch?.[1] ?? draftHtml;
  const editorialMatch = EDITORIAL_SECTION_RE.exec(body);
  const editorialInner = editorialMatch?.[1];
  if (!editorialMatch || editorialInner === undefined) {
    return { bodyHtml: body.trim(), editorialHtml: null };
  }
  const before = body.slice(0, editorialMatch.index);
  const after = body.slice(editorialMatch.index + editorialMatch[0].length);
  return { bodyHtml: (before + after).trim(), editorialHtml: editorialInner.trim() };
}

const TAG_RE = /<[^>]*>/g;

/** Tags stripped, whitespace collapsed. Shared by the length signal and the collapsed-card excerpt. */
export function plainText(html: string): string {
  return html.replace(TAG_RE, " ").replace(/\s+/g, " ").trim();
}

/**
 * Plain-text length of an HTML fragment (tags stripped, whitespace collapsed) — used to decide
 * whether a piece's content is "tweet/LinkedIn-post sized" (show in full) or genuinely long-form
 * (clamp + a modal to read the rest). Collapse-vs-expand of the section itself is no longer
 * driven by this: content that exists is always shown on landing (cmw-piece-draft-visibility).
 * Deliberately crude (regex, not a DOM parser — same tradeoff `parseDraftHtml` already makes)
 * since it only needs to be a rough size signal, not an exact character count.
 */
export function plainTextLength(html: string): number {
  return plainText(html).length;
}

/**
 * First words of the publishable body, for the section summary so a collapsed card still answers
 * "is there a draft, and what does it say" instead of showing only a git SHA. Breaks on a word
 * boundary when it can; empty HTML yields an empty string.
 */
export function draftExcerpt(html: string, maxChars = 96): string {
  const text = plainText(html);
  if (!text) return "";
  if (text.length <= maxChars) return text;
  const sliced = text.slice(0, maxChars);
  const lastSpace = sliced.lastIndexOf(" ");
  const cut = lastSpace > maxChars / 2 ? sliced.slice(0, lastSpace) : sliced;
  return `${cut.trimEnd()}…`;
}
