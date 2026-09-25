"use client";

import * as React from "react";
import Link from "next/link";

import { StageBadge } from "@/components/dashboard/stage-badge";
import { DestinationMatrix } from "@/components/finalize/destination-matrix";
import { FinalizePanel } from "@/components/finalize/finalize-panel";
import { PreFinalizeChecks } from "@/components/finalize/pre-finalize-checks";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { canFinalize, formatsForRequest, toggleFormat } from "@/lib/finalize/formats";
import { DEFAULT_FINALIZE_FORMATS, type FinalizeFormat } from "@/lib/finalize/types";
import type { PieceDetail } from "@/lib/pieces/types";

/**
 * The finalize/outputs screen (cmw-ui-wireframes screen 10; use case J; D13/Item 5): select output
 * formats, review the warn-not-block pre-finalize checks, fire Finalize (source revision +
 * template version get recorded by the finalize step), and browse the outputs list — the final
 * Google Doc of record plus the branded HTML/PDF renders.
 *
 * This is a DISTINCT screen from "Reviews done" (Item 7 / the piece-detail review round) — the
 * piece-detail "Finalize" secondary action links here rather than firing blind, so format
 * selection and the pre-finalize checks are always seen before rendering.
 */
export function FinalizeView({ initial }: { initial: PieceDetail }) {
  const [piece, setPiece] = React.useState(initial);
  const [selected, setSelected] = React.useState<FinalizeFormat[]>([...DEFAULT_FINALIZE_FORMATS]);
  const [submitting, setSubmitting] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  // Explicit success readout (cmw-boss-facing-presentation, MEDIUM): the finalize POST blocks
  // until the render job finishes — name the outcome rather than leaving it to inference.
  const [success, setSuccess] = React.useState<string | null>(null);

  async function handleFinalize() {
    setSubmitting(true);
    setError(null);
    setSuccess(null);
    try {
      const res = await fetch(`/api/pieces/${encodeURIComponent(piece.id)}/finalize`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ formats: formatsForRequest(selected) }),
      });
      if (!res.ok) {
        const body = (await res.json().catch(() => null)) as { error?: string } | null;
        throw new Error(body?.error ?? `request failed (${res.status})`);
      }
      const refreshed = await fetch(`/api/pieces/${encodeURIComponent(piece.id)}`, {
        cache: "no-store",
      });
      if (refreshed.ok) {
        setPiece((await refreshed.json()) as PieceDetail);
      }
      setSuccess("Finalized — outputs are listed under their destinations above.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "something went wrong");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6">
      <div>
        <Button asChild variant="ghost" size="sm" className="mb-2 -ml-2">
          <Link href={`/pieces/${encodeURIComponent(piece.id)}`}>&larr; Back to {piece.title}</Link>
        </Button>
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="font-serif text-3xl font-semibold">Finalize &mdash; {piece.title}</h1>
          <StageBadge stage={piece.stage} round={piece.review_round?.round_number ?? null} />
        </div>
        <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
          This is the render step — the branded palette/typography, generated fresh from{" "}
          <span className="font-mono">visual-identity.md</span>, produces the actual Doc/HTML/PDF
          output only here. The piece-detail preview shows a fixed snapshot of that same identity
          so it never drifts from what a reader sees, but the underlying{" "}
          <span className="font-mono">draft.html</span> content stays plain/semantic and is the
          master; every output below is a disposable, reproducible render.
        </p>
      </div>

      {error ? <Alert className="px-4 py-3">{error}</Alert> : null}
      {success ? (
        <Alert variant="success" className="px-4 py-3">
          {success}
        </Alert>
      ) : null}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div className="flex min-w-0 flex-col gap-6">
          <DestinationMatrix
            piece={piece}
            selected={selected}
            onToggle={(format) => setSelected((prev) => toggleFormat(prev, format))}
            disabled={piece.stage !== "review" || submitting}
          />
          <PreFinalizeChecks piece={piece} />
        </div>

        <div className="flex min-w-0 flex-col gap-6">
          <FinalizePanel
            piece={piece}
            canSubmit={canFinalize(selected)}
            submitting={submitting}
            onFinalize={handleFinalize}
          />

          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Then</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">
                Capture lessons — the machine diffs final vs. published, proposes lessons, you
                accept/edit/reject in one click. After publish, the piece workspace opens a
                Derivatives tab: one anchor can become native formats (LinkedIn, X thread,
                newsletter, …), each with its own council bar. Generation is not built yet; the
                surface is in the IA so publish is not the last step.
              </p>
              <Button asChild variant="outline" size="sm" className="mt-3">
                <Link href={`/pieces/${encodeURIComponent(piece.id)}`}>Back to piece</Link>
              </Button>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
