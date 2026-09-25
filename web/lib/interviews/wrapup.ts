import type { TranscriptTurn } from "@/lib/interviews/types";

/**
 * The v1 wrap-up-nudge trigger (Hendo, 2026-08-10): "I felt that the interviewer would never
 * stop inventing new questions." A simple client-side heuristic — nudge once the active persona
 * has asked {@link WRAPUP_NUDGE_THRESHOLD} questions — standing in for a real assessment against
 * each persona's own "you are done when" criteria (see the interviewer persona docs in the Git
 * brain), which would need a model call this v1 deliberately skips.
 *
 * Isolated here as the ONE seam a future replacement touches: `shouldNudgeWrapUp` is the only
 * thing callers read, so swapping the count heuristic for a real done-when assessment later means
 * changing this function's body, not every place a persona's question count is rendered.
 */

/** Most interviewer personas' "you are done when" criteria (a couple of concrete examples, one
 * number, one throughline) are reachable in well under ten focused questions — 5 nudges early
 * enough to feel like a check-in rather than a wall, while leaving room for a real conversation
 * before it does. */
export const WRAPUP_NUDGE_THRESHOLD = 5;

/** How many questions the active persona has asked so far — every answered turn from that
 * persona, plus the one currently pending (asked, not yet answered), if any. */
export function personaQuestionCount(
  turns: TranscriptTurn[],
  activePersona: string | null,
  hasPendingQuestion: boolean,
): number {
  if (!activePersona) return 0;
  const answered = turns.filter((turn) => turn.persona === activePersona).length;
  return answered + (hasPendingQuestion ? 1 : 0);
}

export function shouldNudgeWrapUp(
  turns: TranscriptTurn[],
  activePersona: string | null,
  hasPendingQuestion: boolean,
): boolean {
  return personaQuestionCount(turns, activePersona, hasPendingQuestion) >= WRAPUP_NUDGE_THRESHOLD;
}
