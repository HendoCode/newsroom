/**
 * Parse the mint form's free-form reviewer-emails textarea into the wire shape
 * (`MintReviewInput.reviewer_emails`) — comma- or newline-separated, order preserved, blanks
 * dropped. An empty result collapses to `null` (mirrors `formatsForRequest`'s omit-when-default
 * convention) since the agents side treats "no emails" and "field omitted" identically.
 */
export function parseReviewerEmails(raw: string): string[] | null {
  const emails = raw
    .split(/[\n,]+/)
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
  return emails.length > 0 ? emails : null;
}
