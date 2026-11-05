import { parseTimestampMs } from "@/lib/format/timestamp";

/** "3h ago" style relative-time formatting, shared across the activity log and any staleness-
 * triage display (dashboard cards, piece detail). Callers capture `now` once (e.g.
 * `React.useMemo(() => new Date(), [])`) rather than reading the clock here, so server- and
 * client-rendered output match. */
export function relativeTime(iso: string, now: Date): string {
  const then = parseTimestampMs(iso);
  if (Number.isNaN(then)) return "";
  const minutes = Math.round((now.getTime() - then) / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  return `${days}d ago`;
}
