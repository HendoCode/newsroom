/**
 * Voice kit domain types (cmw-ui-wireframes screen 11; domain model §1.1 Voice, §1.18 Lesson;
 * D12). Mirror the agents `/api/voices/*` + `/api/lessons/*` wire contracts 1:1 (snake_case,
 * matching the sources/dashboard convention in `lib/sources/types.ts`) so there is no mapping
 * layer.
 */

/** One voice-pack file key — the fixed set `app/git/brain.py`'s `_ALL_VOICE_FILES` knows about.
 * The last two only ever hold content for the shared team voice. */
export type VoiceFileKey =
  | "voice_guide"
  | "style_guide"
  | "content_lessons"
  | "visual_identity"
  | "brand_guidelines";

export interface VoiceListResponse {
  voices: string[];
}

/** The current working-tree content of every pack file for one voice (`null` = file absent —
 * `visual_identity`/`brand_guidelines` on a non-team voice). */
export interface VoicePack {
  slug: string;
  voice_guide: string | null;
  style_guide: string | null;
  content_lessons: string | null;
  visual_identity: string | null;
  brand_guidelines: string | null;
}

export interface VoiceCommit {
  sha: string;
  author_name: string;
  author_email: string;
  date: string;
  message: string;
}

export interface VoiceFileHistoryResponse {
  commits: VoiceCommit[];
}

export interface VoiceFileContentResponse {
  content: string;
}

export interface VoiceFileUpdateInput {
  content: string;
  message: string;
  actor?: string | null;
  actor_name?: string | null;
}

export interface VoiceFileRollbackInput {
  sha: string;
  message?: string | null;
  actor?: string | null;
  actor_name?: string | null;
}

// --- Lessons loop (D12; domain model §1.18) — the per-voice accept/edit/reject gate -----------

export type LessonStatus = "proposed" | "accepted" | "rejected";

export interface Lesson {
  id: string;
  voice: string;
  source_piece_id: string | null;
  observed_change: string;
  generalizable_rule: string;
  status: LessonStatus;
}

export interface LessonDecisionInput {
  rule_text?: string | null;
  actor?: string | null;
}

/** The input the propose step needs that nothing else already holds: the author's actually-
 * published/edited text, diffed against the machine's final Git revision (mirrors
 * `agents/app/schemas.py` `ProposeLessonsRequest`). */
export interface ProposeLessonsInput {
  published_content: string;
  actor?: string | null;
}

export interface ProposeLessonsResult {
  proposed: Lesson[];
}

/** The `voice_guide` pack file is the "DNA the draft writes against"; the rest label the file
 * list (cmw-ui-wireframes screen 11). Order matches the wireframe's file list. */
export const VOICE_FILE_LABELS: Record<VoiceFileKey, string> = {
  voice_guide: "voice-guide.md",
  style_guide: "style-guide.md",
  content_lessons: "content-lessons.md",
  visual_identity: "visual-identity.md",
  brand_guidelines: "brand-guidelines.md",
};

/** Every voice has these three; only the team voice additionally has the brand files (§1.1). */
export const CORE_VOICE_FILES: VoiceFileKey[] = ["voice_guide", "style_guide", "content_lessons"];
export const TEAM_ONLY_VOICE_FILES: VoiceFileKey[] = ["visual_identity", "brand_guidelines"];
