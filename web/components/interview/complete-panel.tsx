import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { InterviewStatus } from "@/lib/interviews/types";

/**
 * "Mark interview complete" (cmw-ui-wireframes screen 3; D16a): a SIGNAL for the piece owner/
 * coordinator, never the draft trigger. Multiple interviews can feed one piece; only a human with
 * authority over the piece presses "enough input" (see the piece-detail "Enough input" → draft
 * card) to actually advance it.
 */
export function CompletePanel({
  status,
  pending,
  onMarkComplete,
}: {
  status: InterviewStatus;
  pending: boolean;
  onMarkComplete: () => void;
}) {
  return (
    <div className="rounded-lg border bg-card p-4">
      <h3 className="font-serif text-base font-semibold">When you&rsquo;re done</h3>
      {status === "complete" ? (
        <div className="mt-2 rounded-md border border-primary/40 bg-primary/10 px-3 py-2 text-sm">
          Marked complete — the piece owner sees this signal.
        </div>
      ) : (
        <Button className="mt-2 w-full" onClick={onMarkComplete} disabled={pending}>
          {pending ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : null}
          Mark interview complete
        </Button>
      )}
      <p className="mt-2 text-[11px] text-muted-foreground">
        <b className="text-foreground">Marking complete tells the owner you&rsquo;re done &mdash; it does not start a draft.</b>{" "}
        You are not deciding whether there&rsquo;s enough to write. A person with authority over the
        piece makes that call. Multiple interviews can feed one piece.
      </p>
    </div>
  );
}
