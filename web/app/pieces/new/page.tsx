import { AppShell } from "@/components/shell/app-shell";
import { NewPieceFromIdea } from "@/components/new-piece/new-piece-from-idea";
import { fetchVoices } from "@/lib/agents-client";
import { requireUser } from "@/lib/session";

/**
 * "New piece from my own idea" (Option B, cmw-narrative-first-entry-point) — a dedicated front
 * door for "I already know what I want to write," separate from "Run the Radar" (`/narrative`).
 * Reached from the dashboard; not a top-level `AppShell` nav item, same convention as `/narrative`
 * and `/spikes/[id]`.
 */
export default async function NewPiecePage() {
  const user = await requireUser();

  let voices: string[] = [];
  try {
    voices = (await fetchVoices()).voices;
  } catch {
    voices = [];
  }

  return (
    <AppShell user={user} active="new-idea">
      <NewPieceFromIdea voices={voices} authorEmail={user.email} />
    </AppShell>
  );
}
