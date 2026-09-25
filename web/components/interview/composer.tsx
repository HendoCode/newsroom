"use client";

import * as React from "react";
import { Loader2, Mic } from "lucide-react";

import { Button } from "@/components/ui/button";
import { TextArea } from "@/components/ui/textarea";
import { OP_LABELS, OP_ORDER } from "@/lib/interviews/ops";
import type { RespondResult } from "@/lib/interviews/types";
import { cn } from "@/lib/utils";

/**
 * The Voice/Type composer (cmw-ui-wireframes screen 3): free-form input that the engine classifies
 * (Sonnet, D6) into a bounded op set, surfaced here as chips. "Voice" reserves the mic affordance
 * for the interviewee's own OS/keyboard dictation (open question B's recommended zero-integration
 * default) — the app only ever receives text either way; there is no in-app audio capture.
 */
export function Composer({
  disabled,
  pending,
  skipDisabled,
  skipPending,
  lastOp,
  onSubmit,
  onSkip,
}: {
  disabled: boolean;
  pending: boolean;
  /** Independent of `disabled`/`pending` — skip is pure roster navigation with no classifier
   * call, so it doesn't need a pending question the way submitting an answer does. */
  skipDisabled: boolean;
  skipPending: boolean;
  lastOp: RespondResult["op"] | null;
  onSubmit: (text: string) => void;
  onSkip: () => void;
}) {
  const [text, setText] = React.useState("");
  const [voiceMode, setVoiceMode] = React.useState(true);

  function submit() {
    const trimmed = text.trim();
    if (!trimmed || disabled || pending) return;
    onSubmit(trimmed);
    setText("");
  }

  return (
    <div className="rounded-lg border bg-card p-4">
      <div className="mb-2.5 flex flex-wrap items-center gap-2.5">
        <div className="inline-flex overflow-hidden rounded-md border">
          <Button
            type="button"
            size="sm"
            variant={voiceMode ? "default" : "outline"}
            onClick={() => setVoiceMode(true)}
            className={cn("h-auto rounded-none px-2.5 py-1 text-xs", !voiceMode && "border-0")}
          >
            <Mic className="mr-1 inline h-3 w-3" aria-hidden />
            Voice
          </Button>
          <Button
            type="button"
            size="sm"
            variant={voiceMode ? "outline" : "default"}
            onClick={() => setVoiceMode(false)}
            className={cn("h-auto rounded-none px-2.5 py-1 text-xs", voiceMode && "border-0")}
          >
            Type
          </Button>
        </div>
        <span className="text-xs text-muted-foreground">
          {voiceMode
            ? "Dictate with your device's keyboard mic — the app only ever receives text."
            : "Type your answer."}{" "}
          One question at a time — answer, then it holds.
        </span>
      </div>

      <TextArea
        value={text}
        onChange={(e) => setText(e.target.value)}
        disabled={disabled || pending}
        placeholder={
          disabled
            ? "Ask the next question to respond…"
            : "Speak or type your answer…"
        }
        className="min-h-16"
      />

      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        <span className="text-[11px] text-muted-foreground">Detected as:</span>
        {OP_ORDER.map((op) => (
          <span
            key={op}
            className={cn(
              "rounded-full border px-2 py-0.5 text-[11px]",
              lastOp === op
                ? "border-foreground bg-foreground text-background"
                : "border-input text-muted-foreground",
            )}
          >
            {OP_LABELS[op]}
          </span>
        ))}
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        <Button onClick={submit} disabled={disabled || pending || !text.trim()}>
          {pending ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : null}
          Submit answer
        </Button>
        <Button variant="ghost" onClick={onSkip} disabled={skipDisabled || skipPending}>
          {skipPending ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : null}
          Skip to next persona
        </Button>
      </div>
    </div>
  );
}
