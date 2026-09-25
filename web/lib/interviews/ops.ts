import type { MetaCommand, RespondResult } from "@/lib/interviews/types";

/**
 * The D6 bounded op set, exactly as the composer surfaces it as chips (cmw-ui-wireframes screen 3;
 * open-decisions D6): every free-form submission classifies into one of these four — never a
 * fifth, and a novel meta-command is still "meta-command" with a recorded note, never dropped.
 */
export const OP_ORDER: RespondResult["op"][] = ["answer", "research-this", "meta-command", "tangent"];

export const OP_LABELS: Record<RespondResult["op"], string> = {
  answer: "Answer",
  "research-this": "Research this",
  "meta-command": "Session request",
  tangent: "Tangent",
};

export const META_COMMAND_LABELS: Record<MetaCommand, string> = {
  "add-interviewer": "Add an interviewer",
  "drop-interviewer": "Drop an interviewer",
  restart: "Restart",
  "stop-for-the-day": "Stop for the day",
  "go-back": "Go back",
  skip: "Skip",
  "switch-piece": "Switch piece",
  other: "Other",
};

export function metaCommandLabel(command: string): string {
  return META_COMMAND_LABELS[command as MetaCommand] ?? command.replace(/[-_]+/g, " ");
}
