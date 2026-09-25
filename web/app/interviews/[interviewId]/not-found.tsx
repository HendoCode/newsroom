import { BrainUnavailableBanner } from "@/components/brain/brain-unavailable-banner";
import { InterviewShell } from "@/components/shell/interview-shell";
import { requireUser } from "@/lib/session";

/**
 * The interview 404 (cmw-boss-facing-presentation, CRITICAL): an interview id that doesn't
 * resolve — most commonly because the interview exists only in the dashboard's placeholder seed
 * data (never backed by real Mongo work-state) or because the agents service / Git brain is
 * unreachable. Either way the surface shows the SAME unified root-cause banner every other
 * brain-dependent surface carries, instead of a bare Next.js 404 that never names why.
 */
export default async function InterviewNotFoundPage() {
  const user = await requireUser();
  return (
    <InterviewShell user={user}>
      <div className="mx-auto flex w-full max-w-lg flex-col gap-4 rounded-lg border border-dashed bg-card p-6">
        <div className="text-center">
          <p className="font-serif text-lg font-semibold">Interview not found</p>
          <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
            This interview link didn&rsquo;t resolve — the id may belong to placeholder (seeded)
            data, or the interview may no longer exist.
          </p>
        </div>
        <BrainUnavailableBanner subject="This interview" />
      </div>
    </InterviewShell>
  );
}
