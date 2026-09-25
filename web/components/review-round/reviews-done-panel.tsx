"use client";

import * as React from "react";
import { Loader2 } from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { ReviewPreviewResult } from "@/lib/review-round/types";

/**
 * The assisted "reviews done" ingest preview + confirm (cmw-ui-wireframes screen 04;
 * open-decisions Item 7): the human declares reviews done, but ONLY after seeing exactly what
 * will fold in — samples of the actual comment/edit text, not just a count. "Confirm — reviews
 * done" is disabled until a preview has successfully loaded, so there is no path to a blind fire.
 */
export function ReviewsDonePanel({
  pieceId,
  disabled,
  onConfirmed,
}: {
  pieceId: string;
  disabled: boolean;
  onConfirmed: () => void;
}) {
  const [preview, setPreview] = React.useState<ReviewPreviewResult | null>(null);
  const [loadingPreview, setLoadingPreview] = React.useState(false);
  const [confirming, setConfirming] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  async function handlePreview() {
    setLoadingPreview(true);
    setError(null);
    setPreview(null);
    try {
      const res = await fetch(`/api/pieces/${encodeURIComponent(pieceId)}/review/preview`, {
        cache: "no-store",
      });
      if (!res.ok) {
        // 404 covers both "no piece" and "no open round" — the friendlier, more actionable
        // message wins over whatever raw detail the agents service returned for either case.
        if (res.status === 404) {
          throw new Error("no open review round to preview — mint a Doc first");
        }
        const body = (await res.json().catch(() => null)) as { error?: string } | null;
        throw new Error(body?.error ?? `request failed (${res.status})`);
      }
      setPreview((await res.json()) as ReviewPreviewResult);
    } catch (e) {
      setError(e instanceof Error ? e.message : "something went wrong");
    } finally {
      setLoadingPreview(false);
    }
  }

  async function handleConfirm() {
    setConfirming(true);
    setError(null);
    try {
      const res = await fetch(`/api/pieces/${encodeURIComponent(pieceId)}/trigger`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ trigger: "reviews-done" }),
      });
      if (!res.ok) {
        const body = (await res.json().catch(() => null)) as { error?: string } | null;
        throw new Error(body?.error ?? `request failed (${res.status})`);
      }
      setPreview(null);
      onConfirmed();
    } catch (e) {
      setError(e instanceof Error ? e.message : "something went wrong");
    } finally {
      setConfirming(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Reviews done</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <p className="text-xs text-muted-foreground">
          Preview exactly what will fold in before committing — the preview is the point (Item 7).
        </p>

        <Button variant="outline" disabled={disabled || loadingPreview} onClick={handlePreview}>
          {loadingPreview ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : null}
          Preview what will fold in
        </Button>

        {preview ? (
          <div className="rounded-md border bg-muted/30 px-3 py-2 text-sm">
            <p className="font-medium text-foreground">
              {preview.comment_count} comment{preview.comment_count === 1 ? "" : "s"} &middot;{" "}
              {preview.edit_count} inline edit{preview.edit_count === 1 ? "" : "s"} detected
            </p>
            {preview.no_changes ? (
              <p className="mt-1 text-muted-foreground">Nothing to fold in yet.</p>
            ) : null}
            {preview.diff_degraded ? (
              <p className="mt-1 text-warning">
                Edit-detection couldn&rsquo;t run (Doc export failed) — comments above are still
                complete, but inline-edit detection may be incomplete.
              </p>
            ) : null}
            {preview.samples.length > 0 ? (
              <ul className="mt-1.5 list-disc pl-5 text-muted-foreground">
                {preview.samples.map((s, i) => (
                  <li key={i} className="text-foreground">
                    {s}
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : null}

        <Button
          className="w-full"
          disabled={disabled || preview === null || confirming}
          onClick={handleConfirm}
          title={preview === null ? "Preview first — there is no path to a blind fire here" : undefined}
        >
          {confirming ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : null}
          Confirm — reviews done
        </Button>

        {disabled ? (
          <p className="text-xs text-muted-foreground">
            Only legal in the <span className="font-mono">review</span> stage.
          </p>
        ) : null}

        {error ? (
          <Alert>{error}</Alert>
        ) : null}
      </CardContent>
    </Card>
  );
}
