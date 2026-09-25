import { Badge } from "@/components/ui/badge";
import type { ReviewRoundRecord } from "@/lib/pieces/types";

/**
 * The between-rounds routing log (open-decisions Item 7): "what happened between rounds and
 * where content went" — every review round the piece has had, most-recent first, each with its
 * own auditable `routing_log` (one line per non-editorial-fix feedback item:
 * `app.review.routing.route_non_fix_items`). Always visible on piece-detail, not gated behind the
 * review-round screen — a piece that has moved past `review` keeps this history in view.
 *
 * Deliberately no clamp/modal here (cmw-modal-long-text-elsewhere): each line is a templated
 * sentence built around `raw.ask.strip()[:_ASK_PREVIEW]` (`app/review/routing.py`,
 * `_ASK_PREVIEW = 80`) — capped by construction to roughly a sentence, never free-form long-form
 * content the way a transcript answer or a council editor's note is. A modal here would add an
 * affordance for content that structurally can't grow long enough to need one.
 */
export function BetweenRoundsLog({ rounds }: { rounds: ReviewRoundRecord[] }) {
  if (rounds.length === 0) {
    return <p className="text-sm text-muted-foreground">No review rounds opened yet.</p>;
  }
  const newestFirst = [...rounds].sort((a, b) => b.round_number - a.round_number);
  return (
    <div className="flex flex-col gap-4">
      {newestFirst.map((round) => (
        <div key={round.round_number} className="flex flex-col gap-1.5">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="font-medium text-foreground">Round {round.round_number}</span>
            <Badge variant="outline">{round.status}</Badge>
            <span className="text-xs text-muted-foreground">
              minted from {round.minted_from_revision} &middot; {round.share_mode === "internal" ? "Internal" : "External"}
            </span>
          </div>
          {round.routing_log.length > 0 ? (
            <ul className="list-disc pl-5 text-sm text-muted-foreground">
              {round.routing_log.map((line, i) => (
                <li key={i} className="text-foreground">
                  {line}
                </li>
              ))}
            </ul>
          ) : (
            <p className="pl-5 text-sm text-muted-foreground">
              No feedback routed in this round yet.
            </p>
          )}
        </div>
      ))}
    </div>
  );
}
