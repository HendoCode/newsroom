import { ExternalLink } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { PieceDetail } from "@/lib/pieces/types";

/**
 * Durable, public outputs from the `finalized → published` HITL button (§1.19-exception — see
 * `agents/app/publish/README.md`). Unlike the disposable finalize render (`OutputsList`, only
 * reachable from `review`), these are real, permanent links, always shown here on piece-detail
 * (the one screen that stays reachable regardless of stage) rather than gated to a stage-specific
 * secondary action — this is the actual surface for Hendo's "a piece needs a way to be done" ask.
 * Renders nothing until the piece has published at least once (`published_release > 0`); since
 * `published` is terminal, that is equivalent to `piece.stage === "published"`.
 */
export function PublishedOutputs({ piece }: { piece: PieceDetail }) {
  if (piece.published_release <= 0) {
    return null;
  }

  const docUrl = piece.published_doc?.url ?? null;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Published outputs</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <p className="text-xs text-muted-foreground">
          Release <span className="font-mono">{piece.published_release}</span>
          {piece.published_at ? (
            <>
              {" "}
              &middot; published <RelativeTime iso={piece.published_at} />
            </>
          ) : null}
          . Generally public by link — bucket listing is off, so nothing indexes these, but the
          link itself needs no signing/token (v1 access-model decision, iterable later).
        </p>
        <div className="flex flex-col divide-y rounded-md border">
          <OutputRow label="Branded HTML (S3)" url={piece.published_html_url} />
          <OutputRow label="PDF (S3)" url={piece.published_pdf_url} />
          <OutputRow label="Published Google Doc" url={docUrl} />
          {/* Drive-side copies, in the piece folder's Published/ subfolder (cmw-drive-piece-folders)
              — parallel to S3 above, present only once GOOGLE_SHARED_DRIVE_ID was configured. */}
          <OutputRow label="Branded HTML (Drive)" url={piece.published_drive_html?.url ?? null} />
          <OutputRow label="PDF (Drive)" url={piece.published_drive_pdf?.url ?? null} />
        </div>
      </CardContent>
    </Card>
  );
}

function OutputRow({ label, url }: { label: string; url: string | null }) {
  return (
    <div className="flex items-center justify-between gap-3 px-3 py-2 text-sm">
      <span className="text-foreground">{label}</span>
      {url ? (
        <Button size="sm" variant="outline" asChild>
          <a href={url} target="_blank" rel="noopener noreferrer">
            Open
            <ExternalLink aria-hidden />
          </a>
        </Button>
      ) : (
        <span className="text-xs text-muted-foreground">not produced this release</span>
      )}
    </div>
  );
}

function RelativeTime({ iso }: { iso: string | null }) {
  if (!iso) return <>unknown</>;
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return <>unknown</>;
  return <>{new Date(then).toLocaleString()}</>;
}
