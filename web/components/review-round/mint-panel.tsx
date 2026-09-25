"use client";

import * as React from "react";
import { ExternalLink, Loader2 } from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { TextArea } from "@/components/ui/textarea";
import { parseReviewerEmails } from "@/lib/review-round/reviewer-emails";
import type { MintReviewResult, ShareMode } from "@/lib/review-round/types";
import { cn } from "@/lib/utils";

/**
 * Mint panel (cmw-ui-wireframes screen 04; D4/D11): freeze the current revision into an
 * internal/external Google Doc, opening a new review round. External sharing HARD-BLOCKS
 * on open clearances (disclosure/clearance risk — engine/feedback-intake.md); ordinary
 * information gaps warn only (D11 v1). The banner below is shown as soon as external is
 * selected, before the human commits.
 */
export function MintPanel({
  pieceId,
  disabled,
  onMinted,
}: {
  pieceId: string;
  disabled: boolean;
  onMinted: () => void;
}) {
  const [shareMode, setShareMode] = React.useState<ShareMode>("internal");
  const [reviewerEmailsRaw, setReviewerEmailsRaw] = React.useState("");
  const [submitting, setSubmitting] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [result, setResult] = React.useState<MintReviewResult | null>(null);

  async function handleMint() {
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch(`/api/pieces/${encodeURIComponent(pieceId)}/review/mint`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          share_mode: shareMode,
          reviewer_emails: parseReviewerEmails(reviewerEmailsRaw),
        }),
      });
      if (!res.ok) {
        const body = (await res.json().catch(() => null)) as { error?: string } | null;
        throw new Error(body?.error ?? `request failed (${res.status})`);
      }
      const data = (await res.json()) as MintReviewResult;
      setResult(data);
      onMinted();
    } catch (e) {
      setError(e instanceof Error ? e.message : "something went wrong");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Mint review Doc</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <div className="flex flex-col gap-2">
          {(
            [
              {
                value: "internal" as const,
                label: "Internal",
                description: "Keeps the editorial block — colleagues see what's still pending.",
              },
              {
                value: "external" as const,
                label: "External",
                description:
                  "Strips the editorial block, adds a DRAFT banner. Hard-blocks on open clearances — warns on ordinary GAPs.",
              },
            ] satisfies { value: ShareMode; label: string; description: string }[]
          ).map((option) => (
            <label
              key={option.value}
              className={cn(
                "flex cursor-pointer items-start gap-3 rounded-md border p-3 transition-colors",
                shareMode === option.value ? "border-primary bg-primary/5" : "border-input",
                disabled ? "cursor-not-allowed opacity-50" : "hover:border-primary/60",
              )}
            >
              <input
                type="radio"
                name="share-mode"
                className="mt-0.5 h-4 w-4 shrink-0 accent-primary"
                checked={shareMode === option.value}
                disabled={disabled}
                onChange={() => setShareMode(option.value)}
              />
              <span className="flex flex-col gap-0.5">
                <span className="text-sm font-medium text-foreground">{option.label}</span>
                <span className="text-xs text-muted-foreground">{option.description}</span>
              </span>
            </label>
          ))}
        </div>

        {shareMode === "external" ? (
          <div className="rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-sm">
            <p className="text-xs font-semibold uppercase tracking-wide text-warning">
              Clearance check enforced
            </p>
            <p className="mt-1 text-foreground">
              External reviewers will see a &ldquo;DRAFT — not for external distribution&rdquo;
              banner and no editorial block. Open clearances (names, figures, or numbers still
              needing owner sign-off) will <strong>hard-block</strong> this mint — resolve them
              first. Ordinary information gaps warn only.
            </p>
          </div>
        ) : null}

        <label className="flex flex-col gap-1">
          <span className="text-xs font-medium text-muted-foreground">
            Reviewer emails (optional — comma or newline separated)
          </span>
          <TextArea
            className="min-h-16"
            value={reviewerEmailsRaw}
            disabled={disabled}
            onChange={(e) => setReviewerEmailsRaw(e.target.value)}
            placeholder="reviewer1@company.com, reviewer2@company.com"
          />
        </label>

        <Button className="w-full" disabled={disabled || submitting} onClick={handleMint}>
          {submitting ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : null}
          Mint review Doc
        </Button>

        {disabled ? (
          <p className="text-xs text-muted-foreground">
            Minting is only legal in the <span className="font-mono">review</span> stage.
          </p>
        ) : null}

        {error ? (
          <Alert>{error}</Alert>
        ) : null}

        {result ? (
          <div className="rounded-md border border-primary/40 bg-primary/5 px-3 py-2 text-sm">
            <p className="font-medium text-foreground">
              Round {result.round_number} opened ({result.share_mode})
            </p>
            {result.doc_url ? (
              <a
                href={result.doc_url}
                target="_blank"
                rel="noopener noreferrer"
                className="mt-1 inline-flex items-center gap-1 text-primary underline-offset-4 hover:underline"
              >
                Open the Doc
                <ExternalLink className="h-3.5 w-3.5" aria-hidden />
              </a>
            ) : null}
            {result.warnings.length > 0 ? (
              <ul className="mt-1.5 list-disc pl-5 text-warning">
                {result.warnings.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
