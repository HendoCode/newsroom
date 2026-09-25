/**
 * The exact bytes `commit_accepted_lesson` will write for a rule.
 *
 * Mirrors `agents/app/git/content.py` `apply_lesson_rule` — keep in lockstep so the voice-kit
 * Git-diff preview matches what Accept actually commits.
 */
export function applyLessonRule(existing: string, ruleText: string): string {
  const separator = existing.endsWith("\n") || existing === "" ? "" : "\n";
  return `${existing}${separator}- ${ruleText}\n`;
}
