"use client";

import * as React from "react";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ExpandToggle } from "@/components/ui/expand-toggle";
import { ToggleSwitch } from "@/components/ui/form-controls";
import { configSummary, credentialLabel, kindLabel, relativeRefreshLabel } from "@/lib/sources/format";
import type { Source } from "@/lib/sources/types";

/**
 * The registry table (cmw-ui-wireframes screen 7). Collapsed to a line or two per row by default —
 * name · kind · classification · on/off · edit — with config/credential/last-refreshed behind the
 * shared `ExpandToggle` (Hendo, 2026-08-10: this table is the authoritative "where do I find a
 * source again" surface, and needs to stay scannable once dozens of sources pile in, not just at
 * today's handful). A refresh error stays ALWAYS visible under its row regardless of expand state
 * — warn-not-block (§5) means that error must never be one click away from disappearing. Includes
 * the disabled/deferred Gmail row the wireframe calls for — it isn't a real connector kind (§9),
 * so it's rendered statically rather than sourced from the registry.
 */
export function SourcesTable({
  sources,
  now,
  onToggle,
  onEdit,
  togglingId,
  refreshErrors = {},
}: {
  sources: Source[];
  now: Date;
  onToggle: (source: Source, enabled: boolean) => void;
  onEdit: (source: Source) => void;
  togglingId: string | null;
  /** Per-source error from the LAST "Refresh sources now" run, keyed by source id — the
   * connectors' refresh is warn-not-block (§5), so this is the only place a bad source's actual
   * error is visible at all (cmw-first-run-ux-batch item 2). */
  refreshErrors?: Record<string, string>;
}) {
  return (
    <div className="overflow-hidden rounded-lg border bg-card">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b bg-muted/40 text-left text-xs uppercase tracking-wide text-muted-foreground">
            <th className="w-8 px-2 py-2" />
            <th className="px-2 py-2 font-medium">Source</th>
            <th className="px-4 py-2 font-medium">On</th>
            <th className="px-4 py-2 font-medium" />
          </tr>
        </thead>
        <tbody>
          {sources.map((source) => (
            <SourceRow
              key={source.id}
              source={source}
              now={now}
              onToggle={onToggle}
              onEdit={onEdit}
              togglingId={togglingId}
              refreshError={refreshErrors[source.id]}
            />
          ))}

          {/* Gmail: disabled/deferred row (§9) — not a real SourceKind, so no live data or actions. */}
          <tr className="text-muted-foreground">
            <td className="w-8 px-2 py-3" />
            <td className="px-2 py-3">
              Gmail <Badge variant="muted">Google</Badge>{" "}
              <span className="text-xs">opt-in, later (§9)</span>
            </td>
            <td className="px-4 py-3">
              <ToggleSwitch checked={false} disabled onChange={() => {}} label="Enable Gmail (deferred)" />
            </td>
            <td className="px-4 py-3">
              <Badge variant="muted">deferred</Badge>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}

function SourceRow({
  source,
  now,
  onToggle,
  onEdit,
  togglingId,
  refreshError,
}: {
  source: Source;
  now: Date;
  onToggle: (source: Source, enabled: boolean) => void;
  onEdit: (source: Source) => void;
  togglingId: string | null;
  refreshError?: string;
}) {
  const [expanded, setExpanded] = React.useState(false);

  return (
    <>
      <tr className={refreshError ? "border-b-0" : "border-b last:border-0"}>
        <td className="w-8 px-2 py-3 align-top">
          <ExpandToggle
            expanded={expanded}
            onToggle={() => setExpanded((v) => !v)}
            label={source.display_name}
          />
        </td>
        <td className="px-2 py-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium">{source.display_name}</span>
            <Badge variant="muted">{kindLabel(source.kind)}</Badge>
            <span className="text-xs text-muted-foreground">
              {source.classification === "read-as-needed" ? "read-as-needed" : "scraped-periodically"}
            </span>
          </div>
          {source.owner ? (
            <div className="text-xs text-muted-foreground">owner: {source.owner}</div>
          ) : null}
        </td>
        <td className="px-4 py-3">
          <ToggleSwitch
            checked={source.enabled}
            disabled={togglingId === source.id}
            onChange={(next) => onToggle(source, next)}
            label={`${source.enabled ? "Disable" : "Enable"} ${source.display_name}`}
          />
        </td>
        <td className="px-4 py-3">
          <Button variant="ghost" size="sm" onClick={() => onEdit(source)}>
            Edit
          </Button>
        </td>
      </tr>
      {expanded ? (
        <tr className={refreshError ? "border-b-0" : "border-b last:border-0"}>
          <td />
          <td colSpan={3} className="px-2 pb-3">
            <dl className="grid grid-cols-1 gap-1 text-sm text-muted-foreground sm:grid-cols-3">
              <div>
                <dt className="text-xs uppercase tracking-wide">Config</dt>
                <dd>{configSummary(source)}</dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wide">Credential</dt>
                <dd>{credentialLabel(source.kind)}</dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wide">Last refreshed</dt>
                <dd>
                  {source.kind === "linkedin-x-clip" ? "—" : relativeRefreshLabel(source.last_refreshed, now)}
                </dd>
              </div>
            </dl>
          </td>
        </tr>
      ) : null}
      {refreshError ? (
        <tr className="border-b last:border-0">
          <td />
          <td colSpan={3} className="px-2 pb-3">
            <Alert>
              Refresh failed for <b>{source.display_name}</b>: {refreshError}
            </Alert>
          </td>
        </tr>
      ) : null}
    </>
  );
}
