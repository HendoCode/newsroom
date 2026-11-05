"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { StageBadge } from "@/components/dashboard/stage-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { relativeTime } from "@/lib/format/relative-time";
import { slugifyHeadline } from "@/lib/spikes/kickoff";
import { obligationKindLabel } from "@/lib/content-workflow/labels";
import type {
  ActorRef,
  CommandEnvelope,
  DeskView,
  HumanObligation,
} from "@/lib/content-workflow/types";
import type { RecentPiece, RecentPiecesResponse } from "@/lib/pieces/types";

/** Content-workflow first-mile tracer (PR #120). Not the home screen — `/newsroom`
 * mounts `Dashboard` (Inbox + Machine strip + Library). Kept so the commit-idea payload tests
 * and `/content-projects` creation path still have a UI. Copy here is operator English, never
 * raw enum names. */
interface Props {
  email: string;
}

export function OperatorDesk({ email }: Props) {
  const router = useRouter();
  const [desk, setDesk] = useState<DeskView | null>(null);
  const [recent, setRecent] = useState<RecentPiecesResponse | null>(null);
  const [recentError, setRecentError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // One clock for the relative-time display, captured on mount (lib/format/relative-time.ts's
  // documented convention) so the strip is stable across re-renders.
  const clock = useMemo(() => new Date(), []);

  useEffect(() => {
    // Independent fetches: a desk failure must not blank the recent-pieces strip and vice versa.
    Promise.allSettled([
      fetch("/api/content-workflow/desk").then((r) => r.json()),
      fetch("/api/pieces/recent").then(async (r) => {
        if (!r.ok) throw new Error("recent pieces unavailable");
        return r.json();
      }),
    ]).then(([deskResult, recentResult]) => {
      if (deskResult.status === "fulfilled") {
        setDesk(deskResult.value);
      } else {
        setDesk({ open_obligations: [], active_work: [], released_projects: [] });
      }
      if (recentResult.status === "fulfilled") {
        setRecent(recentResult.value);
      } else {
        setRecentError("Recent pieces are unavailable right now.");
      }
      setLoading(false);
    });
  }, []);

  async function handleCommitIdea(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    const form = e.currentTarget;
    const title = (form.elements.namedItem("title") as HTMLInputElement).value;
    const narrative = (form.elements.namedItem("narrative") as HTMLTextAreaElement).value;
    try {
      const actor: ActorRef = {
        subject_id: email,
        email,
        display_name: email,
      };
      const slug = slugifyHeadline(title);
      const envelope: CommandEnvelope = {
        schema_version: 1,
        command_type: "commit-idea",
        aggregate: {
          kind: "idea",
          id: `idea-${Date.now()}`,
        },
        actor,
        idempotency_key: `idea-${Date.now()}`,
        expected_version: 0,
        payload: {
          type: "commit-idea",
          project_title: title,
          purpose_brief: {
            proposition: narrative,
            audience: "General",
            angle: "Default",
            desired_outcome: "Audience adopts core proposition",
            why_now: "Relevant operational need",
            constraints: [],
          },
          default_voice_id: "demo-dana",
          authorities: [
            { kind: "direction", assignee: actor, scope: "project" },
            { kind: "input-sufficiency", assignee: actor, scope: "project" },
            { kind: "voice", assignee: actor, scope: "project" },
            { kind: "release", assignee: actor, scope: "project" },
          ],
          anchor_title: title,
          anchor_slug: slug,
          anchor_destination: "blog",
        },
      };

      const res = await fetch("/api/content-workflow/submit", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(envelope),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error || json.detail?.[0]?.msg || "submit failed");
      if (json.outcome === "rejected" && json.rejection?.message) {
        throw new Error(json.rejection.message);
      }
      const projectId =
        json.result_refs?.content_project_id ?? json.result_refs?.project_id ?? "demo-project";
      router.push(`/content-projects/${projectId}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "unknown");
    } finally {
      setSubmitting(false);
    }
  }

  const obligations = desk?.open_obligations ?? [];
  const active = desk?.active_work ?? [];
  const released = desk?.released_projects ?? [];
  const recentPieces = recent?.items ?? [];

  return (
    <div className="space-y-8 p-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Operator Desk</h1>
        <p className="text-muted-foreground">What can I do in the next five minutes?</p>
      </div>

      {/* Recent pieces: the ~6 most recently active pieces, live from the work-state — never a
          hardcoded list (agents/app/pieces.py's /recent has no seed fallback by design). */}
      <Card>
        <CardHeader>
          <CardTitle>Recent pieces</CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="text-muted-foreground">Loading…</div>
          ) : recentError ? (
            <div className="text-sm text-muted-foreground">{recentError}</div>
          ) : recentPieces.length === 0 ? (
            <div className="text-muted-foreground">
              No pieces yet. Commit an idea above, run the Radar, or{" "}
              <Link href="/pieces/new" className="underline">
                start from your own idea
              </Link>
              .
            </div>
          ) : (
            <ul className="divide-y">
              {recentPieces.map((piece: RecentPiece) => (
                <li key={piece.id} className="flex items-center justify-between gap-3 py-2">
                  <Link
                    href={`/pieces/${piece.id}`}
                    className="min-w-0 truncate text-sm font-medium hover:underline"
                  >
                    {piece.title || piece.slug}
                  </Link>
                  <span className="flex shrink-0 items-center gap-2 text-xs text-muted-foreground">
                    <StageBadge stage={piece.stage} />
                    {piece.updated_at ? (
                      <span>active {relativeTime(piece.updated_at, clock)}</span>
                    ) : null}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      {/* First mile */}
      <Card>
        <CardHeader>
          <CardTitle>First mile</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleCommitIdea} className="space-y-3">
            <Input name="title" placeholder="Idea title" required />
            <textarea name="narrative" placeholder="Narrative / purpose" className="w-full rounded border p-2" required />
            <Button type="submit" disabled={submitting}>
              {submitting ? "Starting…" : "Start a project from this idea"}
            </Button>
            {error && <p className="text-sm text-destructive">{error}</p>}
          </form>
          <div className="mt-4 flex flex-wrap gap-2">
            <Button asChild variant="secondary">
              <Link href="/narrative">Run the Radar</Link>
            </Button>
            <Button asChild variant="secondary">
              <Link href="/spikes">Open the Vault</Link>
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Inbox */}
      <Card>
        <CardHeader>
          <CardTitle>Inbox — waiting on you</CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="text-muted-foreground">Loading…</div>
          ) : obligations.length === 0 ? (
            <div className="text-muted-foreground">Nothing needs you right now</div>
          ) : (
            obligations.map((o: HumanObligation) => (
              <div key={o.id} className="border-b py-1 text-sm">
                {obligationKindLabel(o.kind)}
              </div>
            ))
          )}
        </CardContent>
      </Card>

      {/* Machine */}
      <Card>
        <CardHeader>
          <CardTitle>Machine working</CardTitle>
        </CardHeader>
        <CardContent>
          {active.length === 0 ? (
            <div className="text-muted-foreground">No active work</div>
          ) : (
            <div>Active tasks: {active.length}</div>
          )}
        </CardContent>
      </Card>

      {/* Library */}
      <Card>
        <CardHeader>
          <CardTitle>Released projects</CardTitle>
        </CardHeader>
        <CardContent>
          {released.length === 0 ? (
            <div className="text-muted-foreground">No released projects</div>
          ) : (
            released.map((p) => <div key={p.id}>{p.title}</div>)
          )}
        </CardContent>
      </Card>

    </div>
  );
}
