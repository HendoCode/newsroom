"use client";

import * as React from "react";

import { DerivativesSection } from "@/components/piece-detail/derivatives-section";
import { PublishedOutputs } from "@/components/piece-detail/published-outputs";
import { cn } from "@/lib/utils";
import type { PieceDetail } from "@/lib/pieces/types";
import {
  existingFromArtifact,
  type DerivativeArtifact,
  type ExistingDerivative,
} from "@/lib/pieces/derivatives";

type PostPublishTab = "outputs" | "derivatives";

const TABS: { key: PostPublishTab; label: string }[] = [
  { key: "outputs", label: "Outputs" },
  { key: "derivatives", label: "Derivatives" },
];

/**
 * Post-publish mode on the piece workspace: Outputs (durable public links) sit next to
 * Derivatives (natives this anchor can become) so ship is no longer the last tab in the IA.
 *
 * Defaults to Derivatives — the beat the previous IA hid. Outputs stay one click away; they
 * used to be the only thing this mode showed.
 *
 * Mounted only when the piece has actually published (`stage === "published"` or
 * `published_release > 0`). Child artifacts of this piece by default; promote to a top-level
 * piece only when a derivative needs its own owner/review/publish state.
 */
export function PostPublishWorkspace({
  piece,
  existingDerivatives = [],
}: {
  piece: PieceDetail;
  existingDerivatives?: readonly ExistingDerivative[];
}) {
  const [tab, setTab] = React.useState<PostPublishTab>("derivatives");
  const [existing, setExisting] = React.useState<ExistingDerivative[]>(() => [...existingDerivatives]);
  const [busyId, setBusyId] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  const load = React.useCallback(async () => {
    const res = await fetch(`/api/pieces/${encodeURIComponent(piece.id)}/derivatives`, {
      cache: "no-store",
    });
    if (!res.ok) return;
    const artifacts = (await res.json()) as DerivativeArtifact[];
    setExisting(artifacts.map(existingFromArtifact));
  }, [piece.id]);

  React.useEffect(() => {
    void load();
  }, [load]);

  async function handleCommission(destination: string) {
    setBusyId(destination);
    setError(null);
    try {
      const res = await fetch(`/api/pieces/${encodeURIComponent(piece.id)}/derivatives`, {
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
    setBusyId(artifactId);
    setError(null);
    try {
      const res = await fetch(
        `/api/pieces/${encodeURIComponent(piece.id)}/derivatives/${encodeURIComponent(artifactId)}/promote`,
        {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({}),
        },
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
    <div className="flex flex-col gap-4">
      <div role="tablist" aria-label="Post-publish workspace" className="flex flex-wrap gap-1 border-b">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            role="tab"
            id={`post-publish-tab-${t.key}`}
            aria-selected={tab === t.key}
            aria-controls={`post-publish-panel-${t.key}`}
            onClick={() => setTab(t.key)}
            className={cn(
              "border-b-2 px-3 py-2 text-sm font-medium transition-colors",
              tab === t.key
                ? "border-primary text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground",
            )}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div
        role="tabpanel"
        id={`post-publish-panel-${tab}`}
        aria-labelledby={`post-publish-tab-${tab}`}
      >
        {tab === "outputs" ? (
          <PublishedOutputs piece={piece} />
        ) : (
          <DerivativesSection
            existing={existing}
            onCommission={handleCommission}
            onPromote={handlePromote}
            busyId={busyId}
            error={error}
          />
        )}
      </div>
    </div>
  );
}

/** True once the piece has shipped at least once — the gate for post-publish mode. */
export function isPostPublish(piece: Pick<PieceDetail, "stage" | "published_release">): boolean {
  return piece.stage === "released" || piece.stage === "published" || piece.published_release > 0;
}
