"use client";

import * as React from "react";
import Link from "next/link";

import { Badge } from "@/components/ui/badge";

/**
 * The one "seeded data" badge every list/detail surface shares (dashboard, Spikes & Vault,
 * Sources, and — since cmw-boss-facing-presentation — the piece-detail header). Before the
 * piece-detail addition, clicking through from a seeded-data-labelled list lost the placeholder
 * context entirely. When the data IS seeded the badge doubles as the "How do I make this real?"
 * entry point: it links to `/how-it-works`, the page that names exactly what turns the
 * placeholder experience into the real pipeline.
 */
export function SeededDataBadge({
  seeded,
  seededTitle,
}: {
  seeded: boolean;
  /** Surface-specific tooltip override; the default names the general placeholder rule. */
  seededTitle?: string;
}) {
  return (
    <span className="inline-flex flex-wrap items-center gap-2">
      <Badge
        variant="muted"
        data-testid="seeded-data-badge"
        title={
          seeded
            ? seededTitle ??
              "Placeholder work-state until real work is saved — click “how do I make this real?” for what that takes"
            : "Live data"
        }
      >
        {seeded ? "seeded data" : "live data"}
      </Badge>
      {seeded ? (
        <Link
          href="/how-it-works"
          className="text-xs text-muted-foreground underline decoration-dotted underline-offset-2 hover:text-foreground"
        >
          how do I make this real?
        </Link>
      ) : null}
    </span>
  );
}
