/**
 * Read-only Git-brain persona-listing types (§1.2) — for UI selects (the Oracle run panel's
 * persona-adjacent selects, the kickoff screen's persona picker). Mirrors `/api/personas` 1:1.
 *
 * The voice-listing counterpart (`VoiceListResponse`) lives in `@/lib/voice-kit/types` — the
 * voice-kit screen's REST surface (`agents/app/voices.py`) already serves `GET /api/voices` as
 * part of its full view/edit/rollback CRUD, so this module doesn't duplicate it.
 */

export type PersonaKind = "interviewer" | "editor";

export interface PersonaListResponse {
  kind: string;
  personas: string[];
}
