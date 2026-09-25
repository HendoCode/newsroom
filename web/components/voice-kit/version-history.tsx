"use client";

import * as React from "react";

import { Button } from "@/components/ui/button";
import { DiffView } from "@/components/voice-kit/diff-view";
import type { VoiceCommit } from "@/lib/voice-kit/types";

/** Git version history + rollback (cmw-ui-wireframes screen 11). Newest first; the head entry is
 * "now" and has no rollback/compare of its own. Rollback is a Git revert — a new, attributable
 * forward commit, never a history rewrite. */
export function VersionHistory({
  commits,
  currentContent,
  fetchContentAt,
  onRollback,
  rollingBack,
  loading,
}: {
  commits: VoiceCommit[];
  currentContent: string;
  fetchContentAt: (sha: string) => Promise<string>;
  onRollback: (sha: string) => void;
  rollingBack: boolean;
  loading: boolean;
}) {
  const [compareSha, setCompareSha] = React.useState<string | null>(null);
  const [compareContent, setCompareContent] = React.useState<string | null>(null);
  const [compareLoading, setCompareLoading] = React.useState(false);

  async function handleCompare(sha: string) {
    if (compareSha === sha) {
      setCompareSha(null);
      setCompareContent(null);
      return;
    }
    setCompareSha(sha);
    setCompareLoading(true);
    try {
      setCompareContent(await fetchContentAt(sha));
    } finally {
      setCompareLoading(false);
    }
  }

  return (
    <div className="flex flex-col gap-3 rounded-lg border bg-card p-4">
      <h3 className="font-serif text-lg font-semibold">Version history (Git)</h3>
      {loading ? <p className="text-sm text-muted-foreground">Loading…</p> : null}
      {!loading && commits.length === 0 ? (
        <p className="text-sm text-muted-foreground">No commits yet for this file.</p>
      ) : null}
      <ul className="flex flex-col divide-y">
        {commits.map((commit, i) => (
          <li key={commit.sha} className="flex flex-col gap-1.5 py-2 text-xs">
            <div className="flex flex-wrap items-baseline gap-1.5">
              <span className="font-semibold">{i === 0 ? "now" : commit.sha.slice(0, 7)}</span>
              <span className="text-muted-foreground">
                {commit.message} · {commit.author_name} · {new Date(commit.date).toLocaleDateString()}
              </span>
            </div>
            {i > 0 ? (
              <div className="flex flex-wrap gap-2">
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => onRollback(commit.sha)}
                  disabled={rollingBack}
                >
                  Roll back to this version
                </Button>
                <Button size="sm" variant="ghost" onClick={() => handleCompare(commit.sha)}>
                  {compareSha === commit.sha ? "Hide compare" : "Compare"}
                </Button>
              </div>
            ) : null}
            {compareSha === commit.sha ? (
              compareLoading ? (
                <p className="text-muted-foreground">Loading…</p>
              ) : (
                <DiffView before={compareContent ?? ""} after={currentContent} />
              )
            ) : null}
          </li>
        ))}
      </ul>
      <p className="text-xs text-muted-foreground">Rollback is a Git revert — attributable and reversible.</p>
    </div>
  );
}
