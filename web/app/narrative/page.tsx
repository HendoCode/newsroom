import { AppShell } from "@/components/shell/app-shell";
import { NarrativeOracle } from "@/components/narrative/narrative-oracle";
import { fetchVoices } from "@/lib/agents-client";
import { requireUser } from "@/lib/session";

/**
 * Narrative → Oracle entry (use case B; cmw-ui-wireframes screen 8): speak a narrative or run an
 * open scan, then run the on-demand Oracle (D7). Reached from the Spikes & Vault browser's "Run
 * Oracle" link and the dashboard — not a top-level nav item, same convention as `/pieces/[id]` and
 * `/spikes/[id]`.
 */
export default async function NarrativePage({
  searchParams,
}: {
  searchParams: Promise<{ voice?: string }>;
}) {
  const user = await requireUser();
  const { voice } = await searchParams;

  let voices: string[] = [];
  try {
    voices = (await fetchVoices()).voices;
  } catch {
    voices = [];
  }

  const initialVoice = voice && voices.includes(voice)
    ? voice
    : voices[0] ?? "";

  return (
    <AppShell user={user} active="radar">
      <NarrativeOracle voices={voices} authorEmail={user.email} initialVoice={initialVoice} />
    </AppShell>
  );
}
