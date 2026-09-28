import Link from "next/link";

import { BrainUnavailableBanner } from "@/components/brain/brain-unavailable-banner";
import { AppShell } from "@/components/shell/app-shell";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { requireUser } from "@/lib/session";

/** The repo docs base the page's setup pointers link out to. */
const DOCS_BASE = "https://github.com/HendoCode/content-machine/blob/main";

/**
 * How it works / how do I make this real (cmw-boss-facing-presentation, HIGH): the destination
 * the "seeded data" badge's link lands on. Explains what is placeholder vs. real in this v1 POC
 * and names, subsystem by subsystem, exactly what turns the walking-skeleton experience into the
 * real pipeline — the "try me" ask that used to have no home anywhere in the app.
 */
export default async function HowItWorksPage() {
  const user = await requireUser();

  return (
    <AppShell user={user}>
      <div className="mx-auto flex max-w-4xl flex-col gap-6">
        <div>
          <h1 className="font-serif text-3xl font-semibold">How it works</h1>
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
            What you&rsquo;re looking at is a v1 POC. Some of it is real — the pipeline itself,
            the stage machine, the screen you&rsquo;re on — and some of it is placeholder until
            the subsystems below are provisioned. This page names the difference and what turns
            each placeholder into the real thing.
          </p>
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="text-xl">What &ldquo;seeded data&rdquo; means</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-2 text-sm text-muted-foreground">
            <p>
              Until real work is saved, the dashboard, Spikes &amp; Vault, and Sources show
              built-in placeholder rows so every screen is walkable end-to-end. That&rsquo;s what
              the{" "}
              <Badge variant="muted" className="align-middle">
                seeded data
              </Badge>{" "}
              badge marks. Seeded pieces don&rsquo;t advance: their interviews, drafts, and
              review links are illustrative, not live. As soon as the stack has a real datastore
              and one real piece is created, everything you see is genuine work-state.
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-xl">What makes it real</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-4 text-sm">
            <Step n={1} title="The Git brain (voices, personas, interviews, lessons)">
              The single most common gap: without a clone of{" "}
              <RepoLink href="https://github.com/HendoCode/masthead">
                Masthead
              </RepoLink>{" "}
              mounted into the stack, the voice kits, the kickoff voice/persona selectors, the
              Radar&rsquo;s voice pick, and the interview engine all report{" "}
              <i>brain unavailable</i>. Fix: clone the brain repo as a sibling of this checkout{" "}
              <em>before</em> <Mono>docker compose up</Mono> (the default{" "}
              <Mono>BRAIN_HOST_PATH</Mono> already expects that layout).
            </Step>
            <Step n={2} title="A datastore (real pieces, spikes, and work-state)">
              Configure <Mono>MONGO_URL</Mono> for the agents service and the seeded placeholders
              disappear: the dashboard, Spikes &amp; Vault, and Sources read and write real
              work-state, and pieces advance through the pipeline for real.
            </Step>
            <Step n={3} title="LLM credentials (Radar, drafts, councils)">
              The Radar, draft, council, and lessons steps call an LLM provider. With the default
              Bedrock backend an active AWS session is enough (the stack mounts your{" "}
              <Mono>~/.aws</Mono>); the research sidecar additionally wants an{" "}
              <Mono>ANTHROPIC_API_KEY</Mono>.
            </Step>
            <Step n={4} title="A Google grant (review Docs, finalized outputs)">
              Review-round Docs and the finalized clean Doc need the agents service&rsquo;s own
              Google OAuth grant (<Mono>GOOGLE_OAUTH_CLIENT_ID</Mono> /{" "}
              <Mono>_CLIENT_SECRET</Mono> / <Mono>_REFRESH_TOKEN</Mono>) — a separate credential
              from this app&rsquo;s sign-in grant.
            </Step>
            <p className="text-muted-foreground">
              Full local setup walk-through:{" "}
              <RepoLink href={`${DOCS_BASE}/docs/local-dev.md`}>docs/local-dev.md</RepoLink>.
              Brain clone details:{" "}
              <RepoLink href={`${DOCS_BASE}/agents/app/git/README.md`}>
                agents/app/git/README.md
              </RepoLink>
              .
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-xl">Where to check status</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3 text-sm text-muted-foreground">
            <p>
              The <Link href="/voice-kit" className="underline">Voice kits</Link> screen carries a
              brain-version badge when the brain is reachable — and the banner below when it
              isn&rsquo;t. Any screen that depends on the brain degrades to that same banner:
            </p>
            <div className="max-w-xl">
              <BrainUnavailableBanner subject="Anything brain-backed" />
            </div>
          </CardContent>
        </Card>
      </div>
    </AppShell>
  );
}

function Step({ n, title, children }: { n: number; title: string; children: React.ReactNode }) {
  return (
    <div className="flex gap-3">
      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary text-xs font-bold text-primary-foreground">
        {n}
      </span>
      <div className="flex min-w-0 flex-col gap-1">
        <p className="font-medium text-foreground">{title}</p>
        <p className="text-muted-foreground">{children}</p>
      </div>
    </div>
  );
}

function Mono({ children }: { children: React.ReactNode }) {
  return <span className="font-mono text-xs">{children}</span>;
}

function RepoLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <a href={href} className="underline hover:text-foreground" target="_blank" rel="noreferrer">
      {children}
    </a>
  );
}
