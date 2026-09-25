import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { preFinalizeChecks } from "@/lib/finalize/checks";
import type { PieceDetail } from "@/lib/pieces/types";

/**
 * Pre-finalize checks (cmw-ui-wireframes screen 10) — WARN, never block (§5 flexibility
 * principle). Every output strips the editorial/GAP block (the same shared routine external-share
 * will reuse), so open GAPs/clearances are surfaced here rather than hidden by the strip.
 */
export function PreFinalizeChecks({ piece }: { piece: Pick<PieceDetail, "open_gaps" | "open_clearances"> }) {
  const checks = preFinalizeChecks(piece);
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Pre-finalize checks</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-2">
        <div className="rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-sm">
          <p className="text-xs font-semibold uppercase tracking-wide text-warning">
            Warns, does not block
          </p>
          <ul className="mt-1.5 list-disc pl-5">
            {checks.map((c) => (
              <li key={c.id} className={c.severity === "warn" ? "text-foreground" : "text-muted-foreground"}>
                {c.message}
              </li>
            ))}
          </ul>
          <p className="mt-1.5 text-muted-foreground">
            You can finalize anyway — nothing here blocks.
          </p>
        </div>
        <p className="text-xs text-muted-foreground">
          Every output strips the editorial notes block — the same routine the external-share
          path uses.
        </p>
      </CardContent>
    </Card>
  );
}
