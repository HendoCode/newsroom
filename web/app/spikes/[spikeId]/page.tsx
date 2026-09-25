import { notFound } from "next/navigation";

import { SpikeKickoff } from "@/components/spikes/spike-kickoff";
import { AppShell } from "@/components/shell/app-shell";
import { AgentsRequestError, fetchPersonas, fetchSpike, fetchVoices } from "@/lib/agents-client";
import { requireUser } from "@/lib/session";

/**
 * Spike → kickoff (use case C; cmw-ui-wireframes screen 6): pick a spike, create its Piece, assign
 * an internal expert, hand it the agent's pre-selected interviewer personas, and generate a
 * shareable interview link. The dashboard's "Assign expert & kick off" action on a spike card
 * routes here. Auth-gated exactly like every screen (middleware + `requireUser()`).
 */
export default async function SpikeKickoffPage({
  params,
  searchParams,
}: {
  params: Promise<{ spikeId: string }>;
  searchParams: Promise<{ voice?: string }>;
}) {
  const user = await requireUser();
  const { spikeId } = await params;
  const { voice: radarVoice } = await searchParams;

  try {
    const spike = await fetchSpike(spikeId);
    const [voices, interviewerPersonas] = await Promise.all([
      fetchVoices().then(
        (r) => r.voices,
        () => [] as string[],
      ),
      fetchPersonas("interviewer").then(
        (r) => r.personas,
        () => [] as string[],
      ),
    ]);

    return (
      <AppShell user={user}>
        <SpikeKickoff
          spike={spike}
          voices={voices}
          personas={interviewerPersonas}
          radarVoice={radarVoice}
        />
      </AppShell>
    );
  } catch (error) {
    if (error instanceof AgentsRequestError && error.status === 404) {
      notFound();
    }
    return (
      <AppShell user={user}>
        <div className="mx-auto max-w-lg rounded-lg border border-dashed bg-card p-6 text-center">
          <p className="font-serif text-lg font-semibold">Spike unreachable</p>
          <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
            The agents service didn&rsquo;t respond:{" "}
            {error instanceof Error ? error.message : "unknown error"}. Try refreshing, or check
            that the agents service is running.
          </p>
        </div>
      </AppShell>
    );
  }
}
