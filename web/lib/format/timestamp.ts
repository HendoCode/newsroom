/** Parse a backend timestamp as UTC milliseconds since epoch.
 *
 * The agents service serializes naive-UTC datetimes with no zone designator (`app.models.common
 * .utcnow()` — e.g. `"2026-08-11T06:43:52.435000"`, never a trailing `Z`/`+00:00`). Per ECMA-262,
 * `new Date(...)`/`Date.parse(...)` on a date-TIME string with no zone designator is parsed as
 * the *browser's local time*, not UTC — silently wrong everywhere but UTC (confirmed live: in
 * America/Chicago, a timestamp minted 5 minutes ago landed ~5 hours in the future, which
 * `relativeTime` below then read as "just now" instead of "5m ago"). A bare date-only string
 * (no `T`) is unaffected — that form is already spec-defined as UTC. Treat a date-TIME string
 * with no zone designator as UTC by appending `Z` before parsing. */
export function parseTimestampMs(iso: string): number {
  const hasTimeComponent = iso.includes("T");
  const hasZoneDesignator = /[zZ]$|[+-]\d\d:\d\d$/.test(iso);
  const normalized = hasTimeComponent && !hasZoneDesignator ? `${iso}Z` : iso;
  return new Date(normalized).getTime();
}
