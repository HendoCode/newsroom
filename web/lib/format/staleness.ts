import { parseTimestampMs } from "@/lib/format/timestamp";

/** How stale a "last touched by a human" signal is, for the dashboard/piece-detail triage
 * display: `never` (no human touch recorded yet — the strongest signal, e.g. a piece still
 * sitting at its first interactive stage), `stale` (over a week human-cold), or `fresh`
 * (everything else). Deliberately coarse — this drives a visual flag, not a precise metric. */
export type StalenessTier = "fresh" | "stale" | "never";

const STALE_AFTER_MS = 7 * 24 * 60 * 60 * 1000;

export function humanTouchStaleness(lastHumanTouchAt: string | null, now: Date): StalenessTier {
  if (lastHumanTouchAt === null) return "never";
  const then = parseTimestampMs(lastHumanTouchAt);
  if (Number.isNaN(then)) return "never";
  return now.getTime() - then > STALE_AFTER_MS ? "stale" : "fresh";
}
