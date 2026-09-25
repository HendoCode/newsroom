/**
 * The dedicated review-round screen (cmw-ui-wireframes screen 04; D4/D11; open-decisions Item 7).
 * Mirrors the agents `POST/GET /api/pieces/{id}/review/{mint,preview}` wire contract 1:1
 * (`agents/app/review/routes.py`), matching the piece-detail convention of no mapping layer.
 */

import type { ShareMode } from "@/lib/pieces/types";

export type { ShareMode };

/** Mirrors agents `ReviewRoundOut` (`agents/app/schemas.py`). */
export interface ReviewRoundOut {
  round_number: number;
  minted_from_revision: string;
  status: string;
  share_mode: string;
  doc_url: string | null;
  opened_at: string | null;
  routing_log: string[];
}

export interface MintReviewInput {
  share_mode: ShareMode;
  /** `null`/omitted mints with no explicit reviewer share (still creates the Doc + round). */
  reviewer_emails: string[] | null;
}

export interface MintReviewResult {
  round_number: number;
  doc_url: string | null;
  share_mode: ShareMode;
  /** D11: external sharing — clearances hard-block (409), ordinary GAPs warn only.
   * Populated only for `share_mode: "external"` when the piece has open GAPs but no
   * unresolved clearances. */
  warnings: string[];
}

export interface ReviewPreviewResult {
  round_number: number;
  comment_count: number;
  edit_count: number;
  no_changes: boolean;
  /** True when the Doc's plain-text export failed, so edit-detection couldn't run — comments are
   * still shown; this is surfaced, never hidden (§5 "warns, does not block"). */
  diff_degraded: boolean;
  /** Up to 5 sample snippets of what would fold in — the actual point of the preview: a human
   * sanity-checks the agent's reading of the comments, not just a count. */
  samples: string[];
}

/** Mirrors agents `ReviewRoundListResponse` (`agents/app/review/routes.py`) — the round is the
 * primary REST resource (cmw-review-round-ux-impl), the Doc is a child link inside each round. */
export interface ReviewRoundListResponse {
  rounds: ReviewRoundOut[];
}
