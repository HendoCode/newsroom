import { Badge } from "@/components/ui/badge";
import { personaLabel } from "@/lib/interviews/personas";
import type { Interview } from "@/lib/interviews/types";

interface AssignmentPiece {
  title: string;
  voice: string;
  owner: string | null;
  target: string | null;
}

/**
 * The assignment banner + orchestrator state banner (cmw-ui-wireframes screen 3): who's assigned,
 * what it's about, which voice, and the "your words are the source" promise (D16b) — then the
 * one-line VOICE/PIECE/STEP/persona/turn state strip lifted straight from `PROJECT-INSTRUCTIONS.md`.
 */
export function AssignmentBanner({
  piece,
  interview,
}: {
  piece: AssignmentPiece;
  interview: Interview;
}) {
  const activePersona =
    interview.interviewer_personas[interview.current_persona_index] ?? null;
  const yourTurn = interview.status === "open" && Boolean(interview.current_question);

  return (
    <div className="flex flex-col gap-3">
      <div className="rounded-lg border bg-card p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <Badge variant="muted">Your interview</Badge>
            <h1 className="mt-1.5 font-serif text-xl font-semibold">{piece.title}</h1>
            <p className="mt-0.5 text-sm text-muted-foreground">
              Assigned to <b className="text-foreground">{interview.assigned_expert ?? "you"}</b>
              {piece.owner ? (
                <>
                  {" "}
                  by <b className="text-foreground">{piece.owner}</b>
                </>
              ) : null}{" "}
              &middot; voice being written for: <b className="text-foreground">{piece.voice}</b>
            </p>
          </div>
          <p className="max-w-sm text-xs text-muted-foreground">
            <b className="text-foreground">
              {interview.about ?? piece.target ?? "What this is about"}
            </b>
            . Your answers are the source material — the machine structures your words, it invents
            nothing.
          </p>
        </div>
      </div>

      <div className="rounded-md border-l-4 border-primary bg-muted/40 px-4 py-2">
        <span className="font-mono text-xs text-muted-foreground">
          VOICE: {piece.voice} &middot; PIECE: {piece.title} &middot; STEP: interview
          {activePersona ? (
            <>
              {" "}
              &middot; persona: <b className="text-foreground">{personaLabel(activePersona)}</b>
            </>
          ) : null}
          {yourTurn ? (
            <>
              {" "}
              &middot; <b className="text-foreground">your turn</b>
            </>
          ) : null}
        </span>
      </div>
    </div>
  );
}
