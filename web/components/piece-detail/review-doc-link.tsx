import { ExternalLink } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { PieceDetail } from "@/lib/pieces/types";

/**
 * The "Open review Doc" affordance (captain screenshot feedback, 2026-07-30): piece-detail's
 * prominent link to the current round's Google Doc — the surface where review is actually
 * happening. Mirrors the review-round panel's "Open Doc" label/placement (cmw-ui-wireframes
 * screen 04) so the two screens read as one system. Review-only; renders nothing outside the
 * `review` stage. Graceful when `review_round.doc_url` isn't populated yet (e.g. before
 * cmw-review-roundtrip lands): a subtle note instead of a dead button.
 */
export function ReviewDocLink({ piece }: { piece: PieceDetail }) {
  if (piece.stage !== "review") {
    return null;
  }

  const docUrl = piece.review_round?.doc_url ?? null;
  if (!docUrl) {
    return <span className="text-sm text-muted-foreground">no open review Doc yet</span>;
  }

  return (
    <Button asChild variant="secondary" size="sm">
      <a href={docUrl} target="_blank" rel="noopener noreferrer">
        Open review Doc
        <ExternalLink aria-hidden />
      </a>
    </Button>
  );
}
