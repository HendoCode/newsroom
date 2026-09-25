"use client";

import * as React from "react";
import Link from "next/link";
import { ExternalLink } from "lucide-react";

import { StageBadge } from "@/components/dashboard/stage-badge";
import { BetweenRoundsLog } from "@/components/piece-detail/between-rounds-log";
import { MintPanel } from "@/components/review-round/mint-panel";
import { ReviewsDonePanel } from "@/components/review-round/reviews-done-panel";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { stageLabel } from "@/lib/dashboard/actions";
import type { PieceDetail } from "@/lib/pieces/types";

/**
 * The review-round screen (cmw-ui-wireframes screen 04; D4/D11; open-decisions Item 7).
 *
 * ReviewRound is the primary UI object (cmw-review-round-ux-impl): the current round is the
 * primary container at the top, the Google Doc is a child "Open Doc" link inside it, and the
 * mint / reviews-done panels are actions ON the round. The between-rounds log is always visible
 * here (not gated behind piece-detail's collapsed section) so the round history is scannable
 * without leaving this screen.
 *
 * A DISTINCT screen from "Finalize" (Item 7) — the two never share a button, and this one
 * links to Finalize as a separate, clearly-labeled next step rather than the other way around.
 */
export function ReviewRoundView({ initial }: { initial: PieceDetail }) {
  const [piece, setPiece] = React.useState(initial);
  const [refreshing, setRefreshing] = React.useState(false);

  const legalStage = piece.stage === "review";
  const round = piece.review_round;

  async function refetch() {
    setRefreshing(true);
    try {
      const res = await fetch(`/api/pieces/${encodeURIComponent(piece.id)}`, { cache: "no-store" });
      if (res.ok) {
        setPiece((await res.json()) as PieceDetail);
      }
    } finally {
      setRefreshing(false);
    }
  }

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6">
      <div>
        <Button asChild variant="ghost" size="sm" className="mb-2 -ml-2">
          <Link href={`/pieces/${encodeURIComponent(piece.id)}`}>&larr; Back to {piece.title}</Link>
        </Button>
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="font-serif text-3xl font-semibold">Review round &mdash; {piece.title}</h1>
          <StageBadge stage={piece.stage} round={round?.round_number ?? null} />
        </div>
        <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
          A Doc is only authoritative during its open review window — the piece&rsquo;s own history
          stays in Git. Mint, let reviewers mark it up, then preview and confirm before it folds
          back in. This loops until the piece is final.
        </p>
      </div>

      {!legalStage ? (
        <div className="rounded-md border border-dashed bg-muted/30 px-4 py-3 text-sm text-muted-foreground">
          This piece is currently <b className="text-foreground">{stageLabel(piece.stage)}</b>. Minting and
          confirming that reviews are done is only available from <b className="text-foreground">Review</b>.
        </div>
      ) : null}

      {/* The current round is the primary container (cmw-review-round-ux-impl) */}
      {round ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">
              Round {round.round_number}
            </CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <Badge variant={round.status === "open" ? "accent" : "outline"}>
                {round.status}
              </Badge>
              <span className="text-muted-foreground">
                {round.share_mode === "internal" ? "Internal" : "External"} share
              </span>
              <span className="text-muted-foreground font-mono text-xs">
                minted from {round.minted_from_revision}
              </span>
              {round.opened_at ? (
                <span className="text-muted-foreground text-xs">
                  opened {new Date(round.opened_at).toLocaleDateString()}
                </span>
              ) : null}
            </div>

            {/* The Google Doc is a child link inside the round card */}
            {round.doc_url ? (
              <Button asChild variant="secondary" size="sm" className="w-fit">
                <a href={round.doc_url} target="_blank" rel="noopener noreferrer">
                  Open Doc in Google Docs
                  <ExternalLink aria-hidden />
                </a>
              </Button>
            ) : (
              <p className="text-xs text-muted-foreground">No Doc link recorded for this round.</p>
            )}

            {round.routing_log.length > 0 ? (
              <div>
                <p className="text-xs font-medium text-muted-foreground mb-1">Routing log</p>
                <ul className="list-disc pl-5 text-sm text-muted-foreground">
                  {round.routing_log.map((line, i) => (
                    <li key={i} className="text-foreground">{line}</li>
                  ))}
                </ul>
              </div>
            ) : null}
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">No review round yet</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              Mint a Doc to open the first review round — the round is the primary object, the
              Doc is its child.
            </p>
          </CardContent>
        </Card>
      )}

      {/* Actions on the round: mint (opens a new round) and reviews-done (closes the current one) */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <MintPanel pieceId={piece.id} disabled={!legalStage || refreshing} onMinted={refetch} />
        <ReviewsDonePanel pieceId={piece.id} disabled={!legalStage || refreshing} onConfirmed={refetch} />
      </div>

      {/* Round history: always visible on this screen, not collapsed */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">All rounds</CardTitle>
        </CardHeader>
        <CardContent>
          <BetweenRoundsLog rounds={piece.review_rounds} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Then</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Confirming reviews-done re-runs the council on the incorporated edits — back to human
            review. Once the piece clears the bar, Finalize is the distinct render step (never
            this screen, Item 7).
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            <Button asChild variant="outline" size="sm">
              <Link href={`/pieces/${encodeURIComponent(piece.id)}/finalize`}>Finalize</Link>
            </Button>
            <Button asChild variant="outline" size="sm">
              <Link href={`/pieces/${encodeURIComponent(piece.id)}`}>Back to piece</Link>
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
