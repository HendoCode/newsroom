import type { Interview } from "@/lib/interviews/types";

/**
 * Pure persona-menu logic for the interview surface (cmw-ui-wireframes screen 3): the ~10-persona
 * roster with done/active/suggested/off state. No permission gate here — add/drop is a D6
 * meta-command anyone can invoke; "off" just means "not on this interview's pre-selected set yet".
 */

export type PersonaRosterStatus = "done" | "active" | "suggested" | "off";

export interface PersonaRosterEntry {
  name: string;
  label: string;
  status: PersonaRosterStatus;
}

/** Humanize a persona slug for display only ("partner-advocate" -> "Partner Advocate"). */
export function personaLabel(name: string): string {
  return name
    .split("-")
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

/**
 * The full persona menu: the interview's own serial roster (in order) tagged done/active/suggested
 * relative to `current_persona_index`, followed by every other known interviewer persona as "off".
 */
export function personaRoster(interview: Interview, allPersonas: string[]): PersonaRosterEntry[] {
  const onRoster = new Set(interview.interviewer_personas);
  const rostered: PersonaRosterEntry[] = interview.interviewer_personas.map((name, index) => ({
    name,
    label: personaLabel(name),
    status:
      index < interview.current_persona_index
        ? "done"
        : index === interview.current_persona_index
          ? "active"
          : "suggested",
  }));
  const off: PersonaRosterEntry[] = allPersonas
    .filter((name) => !onRoster.has(name))
    .map((name) => ({ name, label: personaLabel(name), status: "off" as const }));
  return [...rostered, ...off];
}
