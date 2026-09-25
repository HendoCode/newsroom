"use client";

import * as React from "react";

import { Button } from "@/components/ui/button";
import { DiffView } from "@/components/voice-kit/diff-view";
import { Input } from "@/components/ui/input";
import { TextArea } from "@/components/ui/textarea";
import { hasChanges } from "@/lib/voice-kit/diff";

/**
 * The markdown view/edit pane (cmw-ui-wireframes screen 11): a View/Edit toggle, a diff against
 * the currently-committed content, and Commit change / Cancel. Keep this component keyed by
 * `${voice}-${fileKey}` in the parent so switching voice/file remounts it with fresh state rather
 * than needing effects to resync (the same recipe as `SourceForm`'s keyed remount).
 */
export function EditorPane({
  fileLabel,
  content,
  onCommit,
  committing,
  commitError,
}: {
  fileLabel: string;
  content: string;
  onCommit: (content: string, message: string) => Promise<boolean>;
  committing: boolean;
  commitError: string | null;
}) {
  const [mode, setMode] = React.useState<"view" | "edit">("view");
  const [draft, setDraft] = React.useState(content);
  const [message, setMessage] = React.useState("");
  const [showDiff, setShowDiff] = React.useState(false);

  async function handleCommit() {
    const ok = await onCommit(draft, message || `edit ${fileLabel}`);
    if (ok) {
      setMode("view");
      setMessage("");
      setShowDiff(false);
    }
  }

  function handleCancel() {
    setDraft(content);
    setMode("view");
    setShowDiff(false);
  }

  return (
    <div className="flex flex-col gap-3 rounded-lg border bg-card p-4">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="font-serif text-xl font-semibold">{fileLabel}</h2>
        <span className="flex-1" />
        <Button variant={mode === "view" ? "default" : "outline"} size="sm" onClick={() => setMode("view")}>
          View
        </Button>
        <Button variant={mode === "edit" ? "default" : "outline"} size="sm" onClick={() => setMode("edit")}>
          Edit
        </Button>
      </div>

      {mode === "view" ? (
        <pre className="max-h-96 overflow-auto whitespace-pre-wrap rounded-md border bg-muted/20 p-3 font-mono text-xs leading-relaxed">
          {content || "(empty)"}
        </pre>
      ) : (
        <TextArea
          aria-label={`Edit ${fileLabel}`}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          rows={16}
          className="font-mono text-xs"
        />
      )}

      {mode === "edit" ? (
        <>
          {showDiff ? <DiffView before={content} after={draft} /> : null}
          <Input
            aria-label="Commit message"
            placeholder="Describe this change (commit message)"
            value={message}
            onChange={(e) => setMessage(e.target.value)}
          />
          {commitError ? <p className="text-sm text-destructive">{commitError}</p> : null}
          <div className="flex flex-wrap gap-2">
            <Button size="sm" onClick={handleCommit} disabled={committing || !hasChanges(content, draft)}>
              {committing ? "Committing…" : "Commit change"}
            </Button>
            <Button variant="ghost" size="sm" onClick={handleCancel} disabled={committing}>
              Cancel
            </Button>
            <Button variant="outline" size="sm" onClick={() => setShowDiff((v) => !v)}>
              {showDiff ? "Hide diff" : "Diff vs current"}
            </Button>
          </div>
        </>
      ) : null}
    </div>
  );
}
