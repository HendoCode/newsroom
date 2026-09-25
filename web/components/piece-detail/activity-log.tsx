import { relativeTime } from "@/lib/format/relative-time";
import type { ActivityEntry } from "@/lib/pieces/types";

/** The activity/routing log (cmw-ui-wireframes screen 2): a synthesized, newest-first view over
 * the piece's council/job/review-round/interview records — see `app.piece_detail.build_activity_log`.
 * `now` is captured once by the caller (not read here) so server- and client-rendered output match. */
export function ActivityLog({ entries, now }: { entries: ActivityEntry[]; now: Date }) {
  if (entries.length === 0) {
    return <p className="text-sm text-muted-foreground">No activity recorded yet.</p>;
  }
  return (
    <div className="flex flex-col gap-1.5 text-sm">
      {entries.map((entry, i) => (
        <div key={i} className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
          <span className="text-muted-foreground">
            <span className="text-foreground">{entry.label}</span>
            {entry.detail ? ` — ${entry.detail}` : null}
          </span>
          {entry.at ? (
            <span className="shrink-0 whitespace-nowrap text-xs text-muted-foreground">
              {relativeTime(entry.at, now)}
            </span>
          ) : null}
        </div>
      ))}
    </div>
  );
}
