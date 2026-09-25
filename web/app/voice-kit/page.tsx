import { AppShell } from "@/components/shell/app-shell";
import { BrainUnavailableBanner } from "@/components/brain/brain-unavailable-banner";
import { VoiceKitScreen } from "@/components/voice-kit/voice-kit-screen";
import {
  fetchBrainStatus,
  fetchPendingLessons,
  fetchVoiceFileHistory,
  fetchVoicePack,
  fetchVoices,
  type BrainStatus,
} from "@/lib/agents-client";
import { requireUser } from "@/lib/session";
import type { Lesson, VoiceCommit, VoicePack } from "@/lib/voice-kit/types";

const DEFAULT_FILE = "voice_guide";

/**
 * The voice-kit screen (cmw-ui-wireframes screen 11; D12): view, edit, and roll back the
 * Git-backed voice packs, and run the proposed-lessons accept/edit/reject gate. Mounts into the
 * app shell exactly like `/sources`. Reads through the BFF client (server-only) — if the agents
 * service or the Git brain is unreachable we still render the shell rather than erroring the
 * whole page; the screen's own voice-switch path retries through `/api/voices`.
 */
export default async function VoiceKitPage() {
  const user = await requireUser();

  let voices: string[] = [];
  try {
    voices = (await fetchVoices()).voices;
  } catch {
    voices = [];
  }

  if (voices.length === 0) {
    return (
      <AppShell user={user} active="voices">
        <section className="flex flex-col gap-4">
          <h1 className="font-serif text-3xl font-semibold">Voice kits</h1>
          <p className="max-w-2xl text-sm text-muted-foreground">
            View, edit, and roll back the voice packs, and run the proposed-lessons
            accept/edit/reject gate — once the brain is reachable.
          </p>
          {/* The unified root-cause banner every brain-dependent surface shares
              (cmw-boss-facing-presentation, CRITICAL) — this screen's original copy was the
              canonical phrasing the banner carries. */}
          <div className="max-w-2xl">
            <BrainUnavailableBanner subject="No voice packs" />
          </div>
        </section>
      </AppShell>
    );
  }

  // `voices.length === 0` returned above, so `voices[0]` is guaranteed present here.
  const initialVoice = voices.includes("demo-mira") ? "demo-mira" : voices[0]!;

  let pack: VoicePack;
  try {
    pack = await fetchVoicePack(initialVoice);
  } catch {
    pack = {
      slug: initialVoice,
      voice_guide: null,
      style_guide: null,
      content_lessons: null,
      visual_identity: null,
      brand_guidelines: null,
    };
  }

  let history: VoiceCommit[] = [];
  try {
    history = (await fetchVoiceFileHistory(initialVoice, DEFAULT_FILE)).commits;
  } catch {
    history = [];
  }

  let lessons: Lesson[] = [];
  try {
    lessons = await fetchPendingLessons(initialVoice);
  } catch {
    lessons = [];
  }

  let brainStatus: BrainStatus | null = null;
  try {
    brainStatus = await fetchBrainStatus();
  } catch {
    brainStatus = null;
  }

  return (
    <AppShell user={user} active="voices">
      <VoiceKitScreen
        user={user}
        initialVoices={voices}
        initialVoice={initialVoice}
        initialPack={pack}
        initialHistory={history}
        initialLessons={lessons}
        brainStatus={brainStatus}
      />
    </AppShell>
  );
}
