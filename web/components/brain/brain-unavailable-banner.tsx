"use client";

import * as React from "react";
import Link from "next/link";

import { Alert } from "@/components/ui/alert";

/**
 * The one destination every "brain unavailable" surface links to. The Git-brain setup steps live
 * in `docs/local-dev.md` ("Git brain" section); this points at that section in the repo so the
 * banner's "how do I fix this" affordance always lands on the real setup doc.
 */
export const BRAIN_SETUP_DOCS_HREF =
  "https://github.com/HendoCode/content-machine/blob/main/docs/local-dev.md#git-brain-voice-kit-lessons-interview";

/**
 * The unified "Brain unavailable" banner (cmw-boss-facing-presentation, CRITICAL).
 *
 * Every surface that depends on the Git brain — the kickoff voice + persona selectors, the Radar
 * voice selector, the voice-kit screen, and the interview deep link — degrades to THIS one banner
 * when the brain is unreachable, instead of each showing its own isolated "no voices available" /
 * "no personas available" copy that never names the shared root cause. The root-cause wording is
 * the voice-kit screen's own ("the agents service or the Git brain may be unavailable") — the one
 * place that already named it — so the message is identical wherever it appears, and it always
 * links to the brain setup docs.
 *
 * `subject` lets a caller name what the user was trying to reach ("voices", "interviewer
 * personas", "this interview") without forking the root-cause sentence itself.
 */
export function BrainUnavailableBanner({ subject }: { subject?: string }) {
  return (
    <Alert variant="warning" data-testid="brain-unavailable-banner">
      <div className="flex min-w-0 flex-col gap-1">
        <p className="font-medium text-foreground">Brain unavailable</p>
        <p className="text-muted-foreground">
          {subject ? `${subject} can’t be reached` : "This can’t be reached"} right now — the
          agents service or the Git brain may be unavailable. Try again shortly, or read the{" "}
          <Link href={BRAIN_SETUP_DOCS_HREF} className="underline hover:text-foreground">
            brain setup docs
          </Link>
          .
        </p>
      </div>
    </Alert>
  );
}
