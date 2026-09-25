"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import type { ReleaseGateView } from "@/lib/content-workflow/types";

/**
 * AuthorizeRelease surface (cmw-release-semantics-impl). The machine never publishes; this is
 * the explicit human action. Authority-model (queued) will gate WHO may submit — this form only
 * records the actor and posts the command.
 *
 * Also the trivial-edit waiver path: a recorded actor+reason keeps an approval valid across a
 * canonical change, instead of requiring council re-approval.
 */
interface Props {
  projectId: string;
  release: ReleaseGateView;
  projectVersion: number;
  email: string;
  onChanged: () => void;
}

export function ReleaseSection({ projectId, release, projectVersion, email, onChanged }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [revision, setRevision] = useState(release.current_revision ?? "");
  const [waiverReason, setWaiverReason] = useState("");
  const [waiverOpen, setWaiverOpen] = useState(release.invalidated);

  async function submitCommand(
    commandType: "accept-final-revision" | "authorize-release" | "record-trivial-edit-waiver",
    payload: Record<string, unknown>,
  ) {
    setBusy(true);
    setError(null);
    try {
      const actor = { subject_id: email, email };
      const res = await fetch("/api/content-workflow/submit", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          schema_version: 1,
          command_type: commandType,
          aggregate: { kind: "content-project", id: projectId },
          actor,
          idempotency_key: `${commandType}-${projectId}-${Date.now()}`,
          expected_version: projectVersion,
          payload: { type: commandType, content_project_id: projectId, piece_id: release.piece_id, ...payload },
        }),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(extractError(json) ?? "The command failed.");
      if (json.outcome === "rejected") {
        throw new Error(json.rejection?.message ?? "The command was rejected.");
      }
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "unknown");
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Release</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        <p className="text-muted-foreground">{release.reason}</p>

        {release.releases.length > 0 ? (
          <ol className="space-y-1">
            {release.releases.map((item) => (
              <li key={item.release_number}>
                Release {item.release_number}
                {item.html_url ? (
                  <>
                    {" "}
                    ·{" "}
                    <a className="underline" href={item.html_url} target="_blank" rel="noreferrer">
                      HTML
                    </a>
                  </>
                ) : null}
                <span className="text-muted-foreground"> · {item.revision.slice(0, 8)}</span>
              </li>
            ))}
          </ol>
        ) : (
          <p className="text-muted-foreground">No Publication Release yet.</p>
        )}

        {error ? <p className="text-destructive">{error}</p> : null}

        {!release.approval_valid ? (
          <form
            className="space-y-2"
            onSubmit={(e) => {
              e.preventDefault();
              void submitCommand("accept-final-revision", { revision: revision.trim() });
            }}
          >
            <label className="block text-sm">
              Revision to accept
              <Input
                value={revision}
                onChange={(e) => setRevision(e.target.value)}
                placeholder="Git revision"
                required
              />
            </label>
            <Button type="submit" disabled={busy || !revision.trim()}>
              Accept final revision
            </Button>
          </form>
        ) : null}

        {release.invalidated ? (
          <div className="space-y-2">
            <Button type="button" variant="outline" onClick={() => setWaiverOpen((v) => !v)}>
              Record a trivial-edit waiver
            </Button>
            {waiverOpen ? (
              <form
                className="space-y-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  void submitCommand("record-trivial-edit-waiver", {
                    from_revision: release.accepted_revision,
                    to_revision: release.current_revision,
                    reason: waiverReason.trim(),
                  });
                }}
              >
                <label className="block text-sm">
                  Why is this edit trivial?
                  <Input
                    value={waiverReason}
                    onChange={(e) => setWaiverReason(e.target.value)}
                    required
                  />
                </label>
                <Button type="submit" disabled={busy || !waiverReason.trim()}>
                  Record waiver
                </Button>
              </form>
            ) : null}
          </div>
        ) : null}

        <Button
          type="button"
          disabled={busy || !release.authorize_enabled}
          onClick={() => void submitCommand("authorize-release", {})}
        >
          {release.releases.length > 0 ? "Authorize another release" : "Authorize release"}
        </Button>
      </CardContent>
    </Card>
  );
}

function extractError(json: unknown): string | null {
  if (!json || typeof json !== "object") return null;
  const rec = json as { error?: unknown; detail?: unknown };
  if (typeof rec.error === "string") return rec.error;
  if (typeof rec.detail === "string") return rec.detail;
  return null;
}
