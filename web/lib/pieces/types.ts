/**
 * Piece-detail domain types (cmw-ui-wireframes screen 2; domain model §1.9/§1.11/§1.13/§1.14).
 *
 * Mirror the agents `GET /api/pieces/{id}` wire contract 1:1 (snake_case), matching the dashboard's
 * existing convention (`lib/dashboard/types.ts`) so there is no mapping layer.
 */

import type { FailedJobRef, PieceStage } from "@/lib/dashboard/types";

export type { PieceStage };

export interface EditorScore {
  editor: string;
  score: number;
  /** slop-allergist / voice-guardian — always present, never skipped (§1.13). */
  mandatory: boolean;
  editorial_fixes: string[];
  information_gaps: string[];
  /** Claims, permissions, or legal/policy checks that require explicit human approval. */
  clearances: string[];
  hard_cap_applied: boolean;
}

export interface CouncilRecord {
  round_number: number;
  /** Autonomous sub-round within round_number (1 = the first scoring pass). */
  iteration: number;
  revision: string;
  aggregate: number | null;
  cost: number;
  /** Why the autonomous loop stopped (quality_bar_met | human_obligation_required |
   * iteration_ceiling | cost_ceiling | no_improvement_possible). */
  stop_reason: string | null;
  /** Human-readable detail for the stop reason. */
  stop_message: string | null;
  editor_scores: EditorScore[];
}

export type ReviewRoundStatus = "open" | "closed" | "archived";
export type ShareMode = "internal" | "external";

/** The final Google Doc of record (D13/use case G; domain model §1.19) — link/metadata only, the
 * same shape as a review round's transient Doc but recorded permanently once a piece is finalized. */
export interface FinalDocRef {
  doc_id: string | null;
  url: string | null;
  share_mode: ShareMode;
}

/** An ordinary Drive file (branded HTML/PDF, cmw-drive-piece-folders) — link/metadata only, no
 * `share_mode` (unlike `FinalDocRef`): visibility comes from Shared Drive membership or the piece
 * folder, not a per-file share grant. */
export interface FinalDriveFileRef {
  file_id: string | null;
  url: string | null;
}

export interface ReviewRoundRecord {
  round_number: number;
  minted_from_revision: string;
  status: ReviewRoundStatus;
  share_mode: ShareMode;
  doc_url: string | null;
  opened_at: string | null;
  /** The auditable "which items were applied, which routed, which vaulted" trail — one line per
   * non-editorial-fix feedback item. Empty until `IncorporateStep` actually closes this round. */
  routing_log: string[];
}

export interface InterviewRecord {
  interview_id: string;
  assigned_expert: string | null;
  status: "open" | "complete";
  about: string | null;
  is_gap_interview: boolean;
}

export type LessonStatus = "proposed" | "accepted" | "rejected";

export interface LessonRecord {
  id: string;
  observed_change: string;
  generalizable_rule: string;
  status: LessonStatus;
  /** The voice the lesson is proposed for + the piece it came from — both ARE on the wire
   * (agents `LessonOut`); optional here only so test fixtures built before they were consumed
   * don't need updating. */
  voice?: string;
  source_piece_id?: string | null;
}

/** One synthesized line in the activity/routing log (derived from real records, not its own store). */
export interface ActivityEntry {
  label: string;
  detail: string | null;
  at: string | null;
}

/** One entry in a piece's retrieval/source list — parsed read-time from the piece's own Git
 * content (agents `app.evidence`), never a separate store. `kind: "footnote"` entries are the
 * draft's `<li id="srcN">` sources the in-text citation chips point at (`chip` carries the
 * visible marker); `kind: "sources-md"` entries are the research citations in `sources.md`,
 * grouped under the file's own headings (`section`). */
export interface EvidenceSource {
  id: string;
  kind: "footnote" | "sources-md";
  chip: string | null;
  label: string;
  urls: string[];
  section: string | null;
}

/** One claim-level citation chip in the draft body: the visible marker (`chip`), the source
 * entry it references (`source_id` — an `EvidenceSource.id`), and the chip's own in-draft
 * anchor (`anchor_id`). */
export interface EvidenceCitation {
  chip: string;
  source_id: string;
  anchor_id: string | null;
}

export interface PieceDetail {
  id: string;
  slug: string;
  title: string;
  voice: string;
  stage: PieceStage;
  owner: string | null;
  assigned_experts: string[];
  origin_spike_id: string | null;
  target: string | null;
  partners: string[];

  open_gaps: number;
  open_clearances: number;
  latest_revision: string | null;

  // Staleness triage (cmw-staleness-timestamps) — same two-timestamp distinction as the
  // dashboard's `QueueItem`: `updated_at` is "when did anything last write this piece" (any
  // write path, including a machine-only batch job); `last_human_touch_at` is "when did a
  // person last act on it" (a stage trigger, or answering/editing an interview turn — never a
  // batch job completing on its own). `null` for either means it hasn't happened yet.
  created_at: string | null;
  updated_at: string | null;
  last_human_touch_at: string | null;

  /** The semantic draft.html master, editorial block included. `null` before a first revision.
   * For a brain-authored direct-content piece this carries the piece.md content rendered to
   * HTML instead (agents `app.piece_md`) — readable either way. */
  draft_html: string | null;

  /** True when this record was registered from a brain-authored drafts/ folder by the
   * brain-draft sync (agents `app.brain_sync`) rather than created through the pipeline. */
  brain_synced: boolean;

  /** True when the response came from the agents service's built-in seed work-state (same
   * store-or-seed fallback as the dashboard's `source` field) rather than a real Mongo document
   * — provenance for the piece-detail "seeded data" badge (cmw-boss-facing-presentation).
   * Optional so fixtures predating the field stay valid; absent means not seeded. */
  seeded?: boolean;

  council: CouncilRecord | null;
  review_round: ReviewRoundRecord | null;
  /** EVERY round the piece has had, ascending — the between-rounds routing log's data source. */
  review_rounds: ReviewRoundRecord[];
  interviews: InterviewRecord[];
  failures: FailedJobRef[];
  lessons: LessonRecord[];
  activity: ActivityEntry[];

  /** The piece's evidence trail (claim-level citation chips + the full retrieval/source list,
   * parsed read-time from draft.html + sources.md by agents `app.evidence`). Optional (not just
   * nullable) so existing test fixtures built before this field existed don't need updating;
   * absent/empty means the piece carries no evidence annotations yet. */
  evidence_sources?: EvidenceSource[];
  evidence_citations?: EvidenceCitation[];

  /** Finalize outputs (D13, use case G/J; §1.19) — `null` until the piece has been finalized at
   * least once. The branded HTML/PDF renders themselves are disposable and not recorded here. */
  final_doc: FinalDocRef | null;
  final_template_version: string | null;
  final_rendered_at: string | null;

  /** The piece's Drive folder under the app's named My-Drive root
   * (cmw-drive-named-folder-scoping) — a convenience "open everything for this piece" link,
   * `null`/absent until GOOGLE_DRIVE_ROOT_FOLDER_NAME is configured server-side
   * and this piece has produced its first Google artifact. Optional (not just nullable, unlike
   * every field above) so existing test fixtures built before this field existed don't need
   * updating. `final_drive_html`/`final_drive_pdf` are the Drive-side copies of the same branded
   * render `final_doc` already tracks — real, unconverted files, not disposable. */
  drive_folder_url?: string | null;
  final_drive_html?: FinalDriveFileRef | null;
  final_drive_pdf?: FinalDriveFileRef | null;

  /** Published outputs (finalized → published HITL button; §1.19-exception — see
   * agents/app/publish/README.md). Unlike `final_doc` above, these ARE durable and public:
   * `published_release` is `0` until the piece has ever been published, then increments on every
   * later publish (each one mints a fresh, immutable S3/Doc snapshot, never overwriting a prior
   * one — an already-shared link keeps resolving). */
  published_release: number;
  published_html_url: string | null;
  published_pdf_url: string | null;
  published_doc: FinalDocRef | null;
  published_at: string | null;
  /** The same release's Drive-side copies, in the piece folder's `Published/` subfolder
   * (cmw-drive-piece-folders) — optional/absent for the same fixture-compatibility reason as
   * `drive_folder_url` above. */
  published_drive_html?: FinalDriveFileRef | null;
  published_drive_pdf?: FinalDriveFileRef | null;

  /** Archive (triage at scale) — orthogonal to `stage`, never a stage value itself. `null`/absent
   * means never archived; a timestamp means hidden from the dashboard queue only — everything
   * else about the piece (including this very page) is unaffected. Optional for the same
   * fixture-compatibility reason as `drive_folder_url` above. */
  archived_at?: string | null;

  /** Set when this Piece was promoted from a child derivative of another piece. Optional so
   * existing fixtures don't need updating. */
  parent_piece_id?: string | null;
  role?: "anchor" | "derivative" | null;
}

/** One row of the desk's recent-pieces strip. Mirrors the agents `GET /api/pieces/recent` wire
 * contract 1:1 (`agents/app/schemas.py`'s `RecentPiece`) — deliberately narrower than `QueueItem`:
 * identity + stage + recency, not the dashboard's full join. Timestamps are the agents service's
 * naive-UTC strings; render through `lib/format/timestamp.ts`'s `parseTimestampMs` (see the
 * cmw-dateparse sharp edge), never a bare `new Date(...)`. */
export interface RecentPiece {
  id: string;
  title: string | null;
  slug: string;
  stage: PieceStage;
  voice: string | null;
  owner: string | null;
  created_at: string | null;
  updated_at: string | null;
  last_human_touch_at: string | null;
}

/** The recent-pieces projection plus provenance (`agents/app/schemas.py`'s
 * `RecentPiecesResponse`). `"store"` = real Mongo work-state; `"none"` = Mongo not configured.
 * There is deliberately NO seed provenance: the strip shows real pieces or an honest empty state,
 * never a hardcoded placeholder list. */
export interface RecentPiecesResponse {
  source: "store" | "none";
  items: RecentPiece[];
}
