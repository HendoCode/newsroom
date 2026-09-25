/**
 * Pure display helpers for the source registry table (cmw-ui-wireframes screen 7). Kept free of
 * React/fetch so they're trivially unit-tested, mirroring `lib/dashboard/actions.ts`.
 */

import type { Source, SourceKind } from "@/lib/sources/types";
import { parseTimestampMs } from "@/lib/format/timestamp";

const KIND_LABELS: Record<SourceKind, string> = {
  gdrive: "Google Drive",
  slack: "Slack",
  "web-rss": "Web / RSS",
  "linkedin-x-clip": "Clip-in",
};

export function kindLabel(kind: SourceKind): string {
  return KIND_LABELS[kind] ?? kind;
}

/** Server-side credential location shown per kind (screen 7) — never a secret value (D14). */
const CREDENTIAL_LABELS: Record<SourceKind, string> = {
  gdrive: "server-side OAuth",
  slack: "bot token (server-side)",
  "web-rss": "none (public)",
  "linkedin-x-clip": "none — no scraper",
};

export function credentialLabel(kind: SourceKind): string {
  return CREDENTIAL_LABELS[kind] ?? "server-side";
}

/** The config-textarea key each Green-connector kind's watched list lives under. */
const CONFIG_LIST_KEY: Partial<Record<SourceKind, string>> = {
  gdrive: "folder_ids",
  slack: "channel_ids",
  "web-rss": "feed_urls",
};

export function configListKey(kind: SourceKind): string | null {
  return CONFIG_LIST_KEY[kind] ?? null;
}

/** One-line summary of a source's config for the table (screen 7's "Config" column). */
export function configSummary(source: Pick<Source, "kind" | "config">): string {
  if (source.kind === "linkedin-x-clip") return "manual paste (below)";
  const key = configListKey(source.kind);
  const value = key ? source.config[key] : undefined;
  if (Array.isArray(value) && value.length > 0) {
    if (source.kind === "web-rss") return `${value.length} feed URL${value.length === 1 ? "" : "s"}`;
    if (source.kind === "gdrive") return `${value.length} folder ID${value.length === 1 ? "" : "s"}`;
    return value.join(", ");
  }
  return "not configured";
}

/** Coarse "Xh/Xd ago" relative time for `last_refreshed`, or "—" when never refreshed. */
export function relativeRefreshLabel(lastRefreshed: string | null, now: Date): string {
  if (!lastRefreshed) return "—";
  const then = parseTimestampMs(lastRefreshed);
  if (Number.isNaN(then)) return "—";
  const diffMs = now.getTime() - then;
  if (diffMs < 0) return "just now";
  const hours = Math.floor(diffMs / (60 * 60 * 1000));
  if (hours < 1) return "just now";
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

/**
 * A pasted Google Drive folder LINK (what a normal business user actually has in hand — the
 * address bar URL, not the bare id buried inside it) is not what `folder_ids` needs on the wire:
 * the connector passes it verbatim into a Drive API query (`'<folder_id>' in parents`), so a full
 * URL there matches nothing (cmw-first-run-ux-batch item 3 — reproduced live, this is exactly
 * what happened). Recognized shapes: `.../drive/folders/<id>`, `.../drive/u/0/folders/<id>`,
 * `.../open?id=<id>`, `...?resourcekey=...`. Falls through to the trimmed input unchanged for a
 * bare id (or anything else) — never silently drops what the user typed.
 */
export function extractDriveFolderId(raw: string): string {
  const trimmed = raw.trim();
  if (!/drive\.google\.com/.test(trimmed)) return trimmed;
  const folderMatch = trimmed.match(/\/folders\/([a-zA-Z0-9_-]+)/);
  if (folderMatch?.[1]) return folderMatch[1];
  const idMatch = trimmed.match(/[?&]id=([a-zA-Z0-9_-]+)/);
  if (idMatch?.[1]) return idMatch[1];
  return trimmed;
}

/** Parse the newline/comma-separated "watched folders/channels/feeds" textarea into a config blob. */
export function parseConfigList(kind: SourceKind, raw: string): Record<string, unknown> {
  const key = configListKey(kind);
  if (!key) return {};
  const values = raw
    .split(/[\n,]/)
    .map((line) => line.trim())
    .filter((line) => line.length > 0)
    .map((line) => (kind === "gdrive" ? extractDriveFolderId(line) : line));
  return { [key]: values };
}

/** Render a source's config list back into the textarea's one-per-line editing format. */
export function configListText(source: Pick<Source, "kind" | "config">): string {
  const key = configListKey(source.kind);
  if (!key) return "";
  const value = source.config[key];
  return Array.isArray(value) ? value.join("\n") : "";
}
