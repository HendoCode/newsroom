import type { PieceDetail } from "@/lib/pieces/types";

/** The at-a-glance panel (cmw-ui-wireframes screen 2): GAPs/clearances, courtesy cost, assigned
 * experts, and partners touched — all attribution/informational, never a permission gate. */
export function AtAGlance({ piece }: { piece: PieceDetail }) {
  return (
    <div className="flex flex-col gap-2 text-sm">
      <Row label="Open gaps" value={piece.open_gaps} />
      <Row label="Open clearances" value={piece.open_clearances} />

      <Row
        label="Assigned expert(s)"
        value={piece.assigned_experts.length > 0 ? piece.assigned_experts.join(", ") : "none yet"}
      />
      {piece.partners.length > 0 ? <Row label="Partners" value={piece.partners.join(" · ")} /> : null}
    </div>
  );
}

function Row({ label, value, note }: { label: string; value: string | number; note?: string }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-md border bg-muted/30 px-3 py-2">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-right font-medium text-foreground">
        {value}
        {note ? <span className="ml-1 text-xs font-normal text-muted-foreground">({note})</span> : null}
      </span>
    </div>
  );
}
