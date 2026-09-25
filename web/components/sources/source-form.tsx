"use client";

import * as React from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, NativeSelect } from "@/components/ui/form-controls";
import { Input } from "@/components/ui/input";
import { TextArea } from "@/components/ui/textarea";
import { configListText, parseConfigList } from "@/lib/sources/format";
import type { Source, SourceClassification, SourceKind } from "@/lib/sources/types";

const KIND_OPTIONS: { value: SourceKind; label: string }[] = [
  { value: "gdrive", label: "Google Drive" },
  { value: "slack", label: "Slack" },
  { value: "web-rss", label: "Web / RSS" },
  { value: "linkedin-x-clip", label: "LinkedIn / X (clip-in)" },
];

const CONFIG_LIST_LABEL: Partial<Record<SourceKind, string>> = {
  gdrive: "Watched folder IDs",
  slack: "Watched channels",
  "web-rss": "Feed URLs",
};

// Kind-specific placeholder — the old shared "Folder IDs, channel names, or feed URLs" text gave
// no indication that a pasted Google Drive folder LINK (what a normal business user actually has,
// not the bare id inside it) was even the right thing to paste (cmw-first-run-ux-batch item 3).
const CONFIG_LIST_PLACEHOLDER: Partial<Record<SourceKind, string>> = {
  gdrive: "Paste the folder's link, e.g. https://drive.google.com/drive/folders/1AbCdEf… — one per line",
  slack: "Channel names, e.g. #partner-eng — one per line",
  "web-rss": "Feed URLs, e.g. https://example.com/feed.xml — one per line",
};

// Only Drive needs the extra "where must this live" guidance — Slack/RSS have no equivalent
// reachability gotcha (a bot invited to a channel, or a public feed URL, is self-evidently
// reachable; a Drive folder silently isn't unless it happens to be shared with the right account).
const GDRIVE_FOLDER_GUIDANCE =
  "Either the folder link or the bare folder id works — a link is parsed automatically. The " +
  "folder must be shared with (or owned by) whichever Google account your org admin connected " +
  "for Drive access, or the Oracle won't be able to see it even though it saves here fine.";

export interface SourceFormValues {
  display_name: string;
  kind: SourceKind;
  classification: SourceClassification;
  lookback_default_days: number;
  config: Record<string, unknown>;
}

/**
 * Add / edit a Green connector, or the LinkedIn/X clip-in source (cmw-ui-wireframes screen 7). This
 * form sets WHAT to read — kind, watched folders/channels/feeds, classification, lookback window —
 * never secrets; credentials are provisioned server-side by an admin (D14). `kind` is locked once a
 * source exists (the backend treats it as immutable — retire and re-add to change it).
 */
export function SourceForm({
  source,
  onSave,
  onRetire,
  onCancel,
  saving,
  error,
  defaultKind,
}: {
  source: Source | null;
  onSave: (values: SourceFormValues) => void;
  onRetire?: () => void;
  onCancel: () => void;
  saving: boolean;
  error: string | null;
  /** Preselect a kind when adding (never used once `source` is set — an existing source's own
   * kind always wins). The "set up a clip-in source" shortcut from the empty clip-in panel uses
   * this to land straight on `linkedin-x-clip` instead of the plain "gdrive" default. */
  defaultKind?: SourceKind;
}) {
  const [displayName, setDisplayName] = React.useState(source?.display_name ?? "");
  const [kind, setKind] = React.useState<SourceKind>(source?.kind ?? defaultKind ?? "gdrive");
  const [classification, setClassification] = React.useState<SourceClassification>(
    source?.classification ?? (defaultKind === "linkedin-x-clip" ? "read-as-needed" : "scraped-periodically"),
  );
  const [lookback, setLookback] = React.useState(source?.lookback_default_days ?? 7);
  const [configText, setConfigText] = React.useState(source ? configListText(source) : "");

  const isLinkedin = kind === "linkedin-x-clip";
  const listLabel = CONFIG_LIST_LABEL[kind];

  function handleKindChange(next: SourceKind) {
    setKind(next);
    if (next === "linkedin-x-clip") setClassification("read-as-needed");
    else if (classification === "read-as-needed") setClassification("scraped-periodically");
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    onSave({
      display_name: displayName,
      kind,
      classification,
      lookback_default_days: lookback,
      config: isLinkedin ? {} : parseConfigList(kind, configText),
    });
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">{source ? "Edit source" : "Add a source"}</CardTitle>
      </CardHeader>
      <CardContent>
        <form className="flex flex-col gap-4" onSubmit={handleSubmit}>
          <Field label="Kind" htmlFor="source-kind" hint="Drive · Slack · Web/RSS · LinkedIn/X clip-in">
            <NativeSelect
              id="source-kind"
              value={kind}
              disabled={source != null}
              onChange={(e) => handleKindChange(e.target.value as SourceKind)}
            >
              {KIND_OPTIONS.map((k) => (
                <option key={k.value} value={k.value}>
                  {k.label}
                </option>
              ))}
            </NativeSelect>
          </Field>

          {isLinkedin ? (
            <p className="rounded-md border border-dashed bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
              This registers the <span className="font-medium text-foreground">channel</span> clips
              attribute to — it doesn&rsquo;t paste any content. To add an actual post, use{" "}
              <span className="font-medium text-foreground">“Clip in a LinkedIn/X post”</span>{" "}
              instead once this is saved.
            </p>
          ) : null}

          <Field label="Display name" htmlFor="source-name">
            <Input
              id="source-name"
              value={displayName}
              placeholder="e.g. Q3 customer call transcripts"
              onChange={(e) => setDisplayName(e.target.value)}
              required
            />
          </Field>

          {!isLinkedin && listLabel ? (
            <Field
              label={listLabel}
              htmlFor="source-config"
              hint={kind === "gdrive" ? GDRIVE_FOLDER_GUIDANCE : "One per line"}
            >
              <TextArea
                id="source-config"
                value={configText}
                onChange={(e) => setConfigText(e.target.value)}
                placeholder={CONFIG_LIST_PLACEHOLDER[kind] ?? "One per line"}
              />
            </Field>
          ) : null}

          <div className="grid grid-cols-2 gap-4">
            <Field label="Classification" htmlFor="source-classification">
              <NativeSelect
                id="source-classification"
                value={classification}
                disabled={isLinkedin}
                onChange={(e) => setClassification(e.target.value as SourceClassification)}
              >
                <option value="scraped-periodically">scraped-periodically</option>
                <option value="read-as-needed">read-as-needed</option>
              </NativeSelect>
            </Field>
            <Field label="Lookback default (days)" htmlFor="source-lookback">
              <Input
                id="source-lookback"
                type="number"
                min={1}
                max={365}
                value={lookback}
                disabled={isLinkedin}
                onChange={(e) => setLookback(Number(e.target.value) || 7)}
              />
            </Field>
          </div>

          <p className="rounded-md border border-dashed bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
            <span className="font-medium text-foreground">Credentials</span> are authorized
            server-side by an org admin (Drive OAuth on the SSO identity / Slack bot token). This
            form configures <span className="font-medium text-foreground">what</span> to read, not
            secrets.
          </p>

          {error ? <Alert>{error}</Alert> : null}

          <div className="flex flex-wrap gap-2">
            <Button type="submit" disabled={saving || !displayName.trim()}>
              {saving ? "Saving…" : "Save source"}
            </Button>
            {source && onRetire ? (
              <Button type="button" variant="outline" onClick={onRetire} disabled={saving}>
                Retire source
              </Button>
            ) : null}
            <Button type="button" variant="ghost" onClick={onCancel} disabled={saving}>
              Cancel
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
