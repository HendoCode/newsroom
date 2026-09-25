"use client";

import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { stageLabel } from "@/lib/dashboard/actions";
import type { PieceDetail } from "@/lib/pieces/types";

/**
 * The Finalize action panel (cmw-ui-wireframes screen 10): records source revision + template
 * version so a re-render is reproducible (D13), then fires the `finalizing` batch job. Visually
 * and behaviorally DISTINCT from "Reviews done" (Item 7) — this is the render step, not another
 * review round.
 */
export function FinalizePanel({
  piece,
  canSubmit,
  submitting,
  onFinalize,
}: {
  piece: PieceDetail;
  canSubmit: boolean;
  submitting: boolean;
  onFinalize: () => void;
}) {
  const legalStage = piece.stage === "review";

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Finalize</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <Field label="Source revision" value={piece.latest_revision ?? "no revision yet"} />
        <Field
          label="Template version"
          value={piece.final_template_version ?? "recorded once this piece has been finalized"}
        />
        <p className="text-xs text-muted-foreground">
          Finalize records which template and brand version produced the output, so a re-render
          is reproducible.
        </p>

        {!legalStage ? (
          <p className="rounded-md border border-dashed bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
            This piece is currently <b className="text-foreground">{stageLabel(piece.stage)}</b>. Finalize is
            only available from <b className="text-foreground">Review</b>
            {piece.stage === "finalized" || piece.stage === "lessons" || piece.stage === "released" || piece.stage === "published"
              ? " — it has already been finalized at least once (see Outputs below)."
              : "."}
          </p>
        ) : null}

        <Button
          className="w-full"
          disabled={!legalStage || !canSubmit || submitting}
          onClick={onFinalize}
        >
          {submitting ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : null}
          Finalize &amp; render outputs
        </Button>
        {legalStage && !canSubmit ? (
          <p className="text-xs text-destructive">Select at least one output format.</p>
        ) : null}
        <p className="text-xs text-muted-foreground">
          Runs the <span className="font-mono">finalizing</span> batch job &rarr; piece becomes{" "}
          <span className="font-mono">finalized</span>. Distinct from &ldquo;Reviews done.&rdquo;
        </p>
      </CardContent>
    </Card>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      <span className="rounded-md border bg-muted/30 px-3 py-2 text-sm font-mono">{value}</span>
    </div>
  );
}
