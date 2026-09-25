import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";

/**
 * Session controls (cmw-ui-wireframes screen 3): "stop for the day" (a D6 meta-command that
 * delegates to the piece machine's pause, resumable at this exact turn) and a "where are we?"
 * reorient — both routed through the real classifier like everything else here, so they're gated
 * on a question being active the same way the persona panel's add/drop is.
 */
export function SessionPanel({
  canAct,
  pending,
  note,
  onStopForDay,
  onWhereAreWe,
}: {
  canAct: boolean;
  pending: boolean;
  note: string | null;
  onStopForDay: () => void;
  onWhereAreWe: () => void;
}) {
  return (
    <div className="rounded-lg border bg-card p-4">
      <h3 className="font-serif text-base font-semibold">Session</h3>
      <div className="mt-2 flex flex-wrap gap-2">
        <Button size="sm" variant="outline" onClick={onStopForDay} disabled={!canAct || pending}>
          {pending ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden /> : null}
          Stop for the day
        </Button>
        <Button size="sm" variant="ghost" onClick={onWhereAreWe} disabled={!canAct || pending}>
          Where are we?
        </Button>
      </div>
      <p className="mt-2 text-[11px] text-muted-foreground">
        &ldquo;Stop for the day&rdquo; pauses the piece, resumable at this exact turn. Reorient
        commands are always available once a question is active.
      </p>
      {note ? <p className="mt-1.5 text-xs text-muted-foreground">{note}</p> : null}
    </div>
  );
}
