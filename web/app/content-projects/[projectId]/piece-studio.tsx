"use client";

import * as React from "react";

import { DerivativesSection } from "@/components/piece-detail/derivatives-section";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

import {
  obligationKindLabel,
  phaseLabel,
  pieceRoleLabel,
} from "@/lib/content-workflow/labels";
import type { PieceWorkspaceItem, ProjectWorkspaceView } from "@/lib/content-workflow/types";
import {
  existingFromArtifact,
  type DerivativeArtifact,
  type ExistingDerivative,
} from "@/lib/pieces/derivatives";

import { ReleaseSection } from "./release-section";
import { ResearchSection } from "./research-section";

interface Props {
  projectId: string;
  initialView: ProjectWorkspaceView | null;
  fetchError: string | null;
  email: string;
}

export function PieceStudio({ projectId, initialView, fetchError, email }: Props) {
  const [view, setView] = React.useState<ProjectWorkspaceView | null>(initialView);

  // Re-read the server-owned projection after a research report / waiver lands — the gate is
  // computed server-side; the UI never derives it locally.
  const reload = React.useCallback(async () => {
    try {
      const res = await fetch(`/api/content-workflow/${projectId}/inspect`, { cache: "no-store" });
      if (res.ok) {
        setView((await res.json()) as ProjectWorkspaceView);
      }
    } catch {
      // A reload hiccup keeps the previous view — never blanks the page.
    }
  }, [projectId]);

  if (fetchError) {
    return (
      <div className="p-6">
        <Card>
          <CardHeader>
            <CardTitle>Project — {projectId}</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-destructive">{fetchError}</p>
            <p className="mt-2 text-sm text-muted-foreground">
              Try again in a moment. If this keeps happening, the project may not have loaded yet.
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (!view) {
    return (
      <div className="p-6 space-y-4">
        <h1>Project — {projectId}</h1>
        <Card>
          <CardHeader><CardTitle>Purpose</CardTitle></CardHeader>
          <CardContent className="text-muted-foreground">No purpose written yet.</CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>What&rsquo;s next</CardTitle></CardHeader>
          <CardContent className="text-muted-foreground">Nothing waiting on you yet.</CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Pieces in this project</CardTitle></CardHeader>
          <CardContent className="text-muted-foreground">No pieces yet.</CardContent>
        </Card>
      </div>
    );
  }

  return (
    <LoadedStudio
      initialView={view}
      projectId={projectId}
      email={email}
      onResearchChanged={reload}
    />
  );
}

function LoadedStudio({
  initialView,
  projectId,
  email,
  onResearchChanged,
}: {
  initialView: ProjectWorkspaceView;
  projectId: string;
  email: string;
  onResearchChanged: () => void;
}) {
  const { project, open_obligations, piece_family, derived_phase, phase_reason } = initialView;
  const topLevelPieces = piece_family.filter(
    (p) => p.role === "anchor" || p.lineage === "promoted",
  );
  const anchor = piece_family.find((p) => p.role === "anchor");
  const showDerivatives = isStudioPostPublish(derived_phase, piece_family);
  const waitingCount = open_obligations.length;

  const [existing, setExisting] = React.useState<ExistingDerivative[]>(() =>
    existingDerivativesFromFamily(piece_family),
  );
  const [busyId, setBusyId] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  const load = React.useCallback(async () => {
    if (!anchor?.id) return;
    const res = await fetch(`/api/pieces/${encodeURIComponent(anchor.id)}/derivatives`, {
      cache: "no-store",
    });
    if (!res.ok) return;
    const artifacts = (await res.json()) as DerivativeArtifact[];
    setExisting(artifacts.map(existingFromArtifact));
  }, [anchor?.id]);

  React.useEffect(() => {
    void load();
  }, [load]);

  async function handleCommission(destination: string) {
    if (!anchor?.id) return;
    setBusyId(destination);
    setError(null);
    try {
      const res = await fetch(`/api/pieces/${encodeURIComponent(anchor.id)}/derivatives`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ destination }),
      });
      if (!res.ok) {
        const body = (await res.json().catch(() => ({ error: "commission failed" }))) as {
          error?: string;
        };
        setError(body.error ?? "commission failed");
        return;
      }
      await load();
    } finally {
      setBusyId(null);
    }
  }

  async function handlePromote(artifactId: string) {
    if (!anchor?.id) return;
    setBusyId(artifactId);
    setError(null);
    try {
      const res = await fetch(
        `/api/pieces/${encodeURIComponent(anchor.id)}/derivatives/${encodeURIComponent(artifactId)}/promote`,
        { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({}) },
      );
      if (!res.ok) {
        const body = (await res.json().catch(() => ({ error: "promote failed" }))) as {
          error?: string;
        };
        setError(body.error ?? "promote failed");
        return;
      }
      await load();
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="space-y-6 p-6">
      <h1 className="text-2xl font-semibold">{project.title}</h1>
      <div className="text-sm text-muted-foreground">
        {phaseLabel(derived_phase)}
        {phase_reason ? ` · ${phase_reason}` : ""}
      </div>

      <Card>
        <CardHeader><CardTitle>Purpose</CardTitle></CardHeader>
        <CardContent className="space-y-1 text-sm">
          <p>{project.purpose_brief.proposition}</p>
          <p className="text-muted-foreground">
            {project.purpose_brief.audience} · {project.purpose_brief.angle}
          </p>
        </CardContent>
      </Card>

      {initialView.research ? (
        <ResearchSection
          projectId={projectId}
          research={initialView.research}
          projectVersion={project.version}
          email={email}
          onChanged={onResearchChanged}
        />
      ) : null}

      {initialView.release ? (
        <ReleaseSection
          projectId={projectId}
          release={initialView.release}
          projectVersion={project.version}
          email={email}
          onChanged={onResearchChanged}
        />
      ) : null}

      <Card>
        <CardHeader><CardTitle>What&rsquo;s next</CardTitle></CardHeader>
        <CardContent>
          {waitingCount === 0 ? (
            <p className="text-muted-foreground">Nothing needs your decision right now.</p>
          ) : (
            <ul className="space-y-1 text-sm">
              <li className="text-muted-foreground">
                {waitingCount === 1
                  ? "1 decision waiting on you"
                  : `${waitingCount} decisions waiting on you`}
              </li>
              {open_obligations.map((o) => (
                <li key={o.id}>{obligationKindLabel(o.kind)}</li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Pieces in this project</CardTitle></CardHeader>
        <CardContent>
          {topLevelPieces.length === 0 ? (
            <div className="text-muted-foreground">No pieces yet.</div>
          ) : (
            topLevelPieces.map((p) => (
              <div key={p.id} className="border-b py-1 text-sm">
                {p.title} · {pieceRoleLabel(p.role)} · {phaseLabel(p.derived_phase)}
              </div>
            ))
          )}
        </CardContent>
      </Card>

      {showDerivatives ? (
        <DerivativesSection
          existing={existing}
          onCommission={anchor?.id ? handleCommission : undefined}
          onPromote={anchor?.id ? handlePromote : undefined}
          busyId={busyId}
          error={error}
        />
      ) : null}
    </div>
  );
}

function existingDerivativesFromFamily(family: PieceWorkspaceItem[]): ExistingDerivative[] {
  return family
    .filter((p) => p.role === "derivative")
    .map((p) => ({
      id: p.id,
      title: p.title,
      destination: p.destination,
      phase: p.derived_phase,
      lineage: p.lineage ?? "child",
      promoted_piece_id: p.promoted_piece_id ?? null,
      href:
        p.lineage === "promoted"
          ? `/pieces/${encodeURIComponent(p.promoted_piece_id ?? p.id)}`
          : undefined,
    }));
}

function isStudioPostPublish(derivedPhase: string, family: PieceWorkspaceItem[]): boolean {
  if (derivedPhase === "completed") return true;
  return family.some((p) => p.derived_phase === "released");
}
