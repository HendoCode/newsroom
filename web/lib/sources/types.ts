/**
 * Source registry domain types (docs/design.md D7/D8/D14; cmw-open-decisions §Item-6;
 * cmw-ui-wireframes screen 7).
 *
 * Mirror the agents `/api/sources` + `/api/connectors/*` wire contracts 1:1 (snake_case, matching
 * the dashboard convention in `lib/dashboard/types.ts`) so there is no mapping layer. Credentials
 * never appear here — `config` sets WHAT to read, never secrets (D14); they live server-side only.
 */

export type SourceKind = "gdrive" | "slack" | "web-rss" | "linkedin-x-clip";

/** The §4A key distinction: harvested on refresh vs pulled only when a run needs it. */
export type SourceClassification = "scraped-periodically" | "read-as-needed";

/** One source-registry entry. `config` is kind-specific and never carries credentials. */
export interface Source {
  id: string;
  display_name: string;
  kind: SourceKind;
  classification: SourceClassification;
  enabled: boolean;
  lookback_default_days: number;
  config: Record<string, unknown>;
  owner: string | null;
  last_refreshed: string | null;
}

export interface SourceListResponse {
  /** "seed" = built-in placeholder rows; "store" = real Mongo work-state. */
  source: "store" | "seed";
  items: Source[];
}

export interface SourceCreateInput {
  display_name: string;
  kind: SourceKind;
  classification: SourceClassification;
  lookback_default_days?: number;
  config?: Record<string, unknown>;
  owner?: string | null;
}

export interface SourceUpdateInput {
  display_name?: string;
  classification?: SourceClassification;
  enabled?: boolean;
  lookback_default_days?: number;
  config?: Record<string, unknown>;
  owner?: string | null;
}

export interface SourceDeleteResponse {
  id: string;
  deleted: boolean;
}

// --- Connectors (D8): on-demand refresh + credential-free clip-in -----------------------------

export interface RefreshRequestInput {
  source_id?: string;
  kinds?: string[];
  lookback_days?: number;
}

export interface RefreshResult {
  source_id: string;
  kind: string;
  ingested: number;
  skipped: number;
  error: string | null;
}

export interface RefreshResponse {
  refreshed: RefreshResult[];
}

export interface ClipInInput {
  source_id: string;
  content: string;
  url?: string | null;
  author?: string | null;
  content_date?: string | null;
  tags?: string[];
  title?: string | null;
}

export interface ClipInResponse {
  id: string;
  classification: string;
  indexed: boolean;
}
