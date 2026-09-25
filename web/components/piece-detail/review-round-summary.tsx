import Link from "next/link";
import { ExternalLink } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { PieceDetail } from "@/lib/pieces/types";

/**
 * ReviewRound as the primary UI object (cmw-review-round-ux-impl): the current round is the
 * card, the Google Doc is a child "Open Doc" link inside it — the reverse of the old
 * ``ReviewDocLink`` component, which treated the Doc as the primary affordance.
 *
 * Shows on piece-detail whenever the piece is in the ``review`` stage, whether or not a round
 * has been minted yet. When a round is open, the round number / status / share mode are the
 * headline, and the Doc link is a secondary button. When no round is open yet, the card
 * points to the review-round page to mint one.
 *
 * Deliberately never rendered outside the ``review`` stage — the card is a review-stage
 * affordance, not a piece-lifetime fixture.
 */
export function ReviewRoundSummary({ piece }: { piece: PieceDetail }) {
  if (piece.stage !== "review") {
    return null;
  }

  const round = piece.review_round;
  const hasDoc = Boolean(round?.doc_url);

  return (
    <div className="flex items-center gap-2 rounded-md border bg-card px-3 py-1.5">
      <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {round ? `Round ${round.round_number}` : "Review"}
      </span>

      {round ? (
        <>
          <Badge variant={round.status === "open" ? "accent" : "outline"}>
            {round.status}
          </Badge>
          <span className="text-xs text-muted-foreground">
            {round.share_mode === "internal" ? "Internal" : "External"}
          </span>
          {round.minted_from_revision ? (
            <span className="text-xs text-muted-foreground font-mono">
              {round.minted_from_revision}
            </span>
          ) : null}
        </>
      ) : (
        <Badge variant="outline">no round yet</Badge>
      )}

      {/* The Google Doc is a child link, never the primary button */}
      {hasDoc ? (
        <Button asChild variant="secondary" size="sm">
          <a href={round!.doc_url!} target="_blank" rel="noopener noreferrer">
            Open Doc
            <ExternalLink aria-hidden />
          </a>
        </Button>
      ) : null}

      <Button asChild variant="ghost" size="sm">
        <Link href={`/pieces/${encodeURIComponent(piece.id)}/review`}>
          {round ? "Manage round" : "Mint round"}
        </Link>
      </Button>
    </div>
  );
}