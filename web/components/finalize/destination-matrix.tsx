"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { FINALIZE_FORMAT_OPTIONS, type FinalizeFormat } from "@/lib/finalize/types";
import type { PieceDetail } from "@/lib/pieces/types";
import { cn } from "@/lib/utils";

/**
 * The finalize output chooser as a destination-by-format matrix (cmw-drive-piece-folders,
 * replacing the old FormatSelection + OutputsList pair on this screen): rows are formats
 * (Branded HTML / PDF / Clean Google Doc), columns are destinations (Drive / S3).
 *
 * Drive's three checkboxes are the real "what to produce this run" chooser — they drive
 * `Job.formats` exactly as the old FormatSelection did (see `lib/finalize/formats.ts`, unchanged).
 * S3 is populated only by the separate, later "Publish" HITL action (piece-detail, not this
 * screen) — its two cells are status/links only, never independently triggerable from here, since
 * finalize has no mechanism to write to S3 on its own. There is no S3×Doc cell: a Doc is a Drive
 * object (Hendo's call).
 *
 * Each produced cell also links straight to the artifact once one exists, folding in what
 * OutputsList/a slice of PublishedOutputs used to show separately — one grid instead of three
 * cards for "what will this produce, and what has it already produced."
 */
export function DestinationMatrix({
  piece,
  selected,
  onToggle,
  disabled = false,
}: {
  piece: PieceDetail;
  selected: readonly FinalizeFormat[];
  onToggle: (format: FinalizeFormat) => void;
  disabled?: boolean;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Outputs &amp; destinations</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {piece.drive_folder_url ? (
          <a
            href={piece.drive_folder_url}
            target="_blank"
            rel="noreferrer"
            className="text-sm font-medium text-primary hover:underline"
          >
            Open this piece&rsquo;s Drive folder &#8599;
          </a>
        ) : (
          <p className="text-xs text-muted-foreground">
            No Drive folder yet — one is created automatically the first time this piece produces a
            Google artifact.
          </p>
        )}

        <div className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-4 gap-y-1 text-xs font-medium text-muted-foreground sm:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_minmax(0,1fr)]">
          <span className="hidden sm:block">Format</span>
          <span>Drive</span>
          <span className="hidden sm:block">S3</span>
        </div>

        <div className="flex flex-col divide-y rounded-md border">
          {FINALIZE_FORMAT_OPTIONS.map((option) => {
            const checked = selected.includes(option.value);
            return (
              <div
                key={option.value}
                className={cn(
                  "grid grid-cols-[minmax(0,1fr)_auto] items-start gap-3 p-3 sm:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_minmax(0,1fr)]",
                  checked && "bg-primary/5",
                )}
              >
                <label
                  className={cn(
                    "flex cursor-pointer items-start gap-3",
                    disabled && "cursor-not-allowed opacity-50",
                  )}
                >
                  <input
                    type="checkbox"
                    className="mt-0.5 h-4 w-4 shrink-0 accent-primary"
                    checked={checked}
                    disabled={disabled}
                    onChange={() => onToggle(option.value)}
                  />
                  <span className="flex flex-col gap-0.5">
                    <span className="text-sm font-medium text-foreground">{option.label}</span>
                    <span className="text-xs text-muted-foreground">{option.description}</span>
                  </span>
                </label>

                <DestinationCell link={driveLinkFor(piece, option.value)} emptyLabel="not yet produced" />

                {option.value === "doc" ? (
                  <span className="text-xs text-muted-foreground sm:col-start-3">
                    n/a — a Doc is a Drive object
                  </span>
                ) : (
                  <DestinationCell link={s3LinkFor(piece, option.value)} emptyLabel="not published yet" />
                )}
              </div>
            );
          })}
        </div>

        {piece.final_rendered_at ? (
          <p className="text-xs text-muted-foreground">
            Last rendered <RelativeTime iso={piece.final_rendered_at} /> &middot; template{" "}
            <span className="font-mono">{piece.final_template_version ?? "unknown"}</span> &middot;
            source revision <span className="font-mono">{piece.latest_revision ?? "unknown"}</span>
          </p>
        ) : (
          <p className="text-xs text-muted-foreground">No outputs yet — finalize this piece to produce them.</p>
        )}
      </CardContent>
    </Card>
  );
}

function driveLinkFor(piece: PieceDetail, format: FinalizeFormat): string | null {
  if (format === "doc") return piece.final_doc?.url ?? null;
  if (format === "html") return piece.final_drive_html?.url ?? null;
  return piece.final_drive_pdf?.url ?? null;
}

function s3LinkFor(piece: PieceDetail, format: FinalizeFormat): string | null {
  if (format === "html") return piece.published_html_url ?? null;
  if (format === "pdf") return piece.published_pdf_url ?? null;
  return null;
}

function DestinationCell({ link, emptyLabel }: { link: string | null; emptyLabel: string }) {
  if (!link) {
    return <span className="text-xs text-muted-foreground">{emptyLabel}</span>;
  }
  return (
    <a href={link} target="_blank" rel="noreferrer" className="text-xs font-medium text-primary hover:underline">
      Open &#8599;
    </a>
  );
}

function RelativeTime({ iso }: { iso: string | null }) {
  if (!iso) return <>unknown</>;
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return <>unknown</>;
  return <>{new Date(then).toLocaleString()}</>;
}
