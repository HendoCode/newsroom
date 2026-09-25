/**
 * Shared "is this turn answer long enough to clamp" signal for both the piece-detail transcript
 * record (read-only, `components/piece-detail/transcript-record.tsx`) and the interactive
 * interview surface's transcript panel (`components/interview/transcript-panel.tsx`) — Hendo's
 * explicit ask, made while first driving interviews, for "a modal popup of the complete text"
 * once a long research-derived answer stopped fitting inline. Deliberately a smaller threshold
 * than `lib/pieces/draft-html.ts`'s `LONG_CONTENT_CHARS` (2000): a turn renders inside a compact
 * list row alongside several other turns, not as the page's own content, so it needs to clamp much
 * earlier to keep that list scannable.
 */
export const LONG_ANSWER_CHARS = 400;

export function isLongAnswer(answer: string): boolean {
  return answer.length > LONG_ANSWER_CHARS;
}
