"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { Field, NativeSelect } from "@/components/ui/form-controls";
import { Input } from "@/components/ui/input";
import { TextArea } from "@/components/ui/textarea";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { BrainUnavailableBanner } from "@/components/brain/brain-unavailable-banner";

/**
 * "New piece from my own idea" (Option B, cmw-narrative-first-entry-point) — the front door for
 * "I already know what I want to write," separate from "Run the Radar" (`/narrative`). Speaks a
 * narrative and mints its Spike directly (`POST /api/spikes/from-narrative` — no Oracle ranking
 * run), then lands straight on that spike's own 5-step kickoff page (`/spikes/[spikeId]`) —
 * never the ranked-spikes review table. The kickoff page is unchanged: it already renders the
 * originating narrative (`NarrativeReveal`) and creates the Piece via the existing `pick` step.
 *
 * The Spike is still minted here, not skipped — `DraftStep._purpose_block` (`agents/`) has no
 * purpose block at all for a piece with no origin Spike, which is exactly what let a past draft
 * come back about an unrelated subject (see that module's docstring). Skipping ranking is fine;
 * skipping the Spike is not.
 */
export function NewPieceFromIdea({
  voices,
  authorEmail,
}: {
  voices: string[];
  authorEmail: string;
}) {
  const router = useRouter();
  const [headline, setHeadline] = React.useState("");
  const [seedText, setSeedText] = React.useState("");
  const [audience, setAudience] = React.useState("");
  const [angle, setAngle] = React.useState("");
  const [voice, setVoice] = React.useState(voices[0] ?? "");
  const [submitting, setSubmitting] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const canSubmit = headline.trim() !== "" && seedText.trim() !== "" && !submitting;

  async function handleSubmit() {
    setSubmitting(true);
    setError(null);
    try {
      const narrativeRes = await fetch("/api/narratives", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          seed_text: seedText,
          audience: audience || null,
          angle: angle || null,
        }),
      });
      const narrativeBody: unknown = await narrativeRes.json();
      if (!narrativeRes.ok) {
        throw new Error(
          narrativeBody && typeof narrativeBody === "object" && "error" in narrativeBody
            ? String((narrativeBody as { error: unknown }).error)
            : "could not save your narrative",
        );
      }
      const narrativeId = (narrativeBody as { id: string }).id;

      const spikeRes = await fetch("/api/spikes/from-narrative", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ narrative_id: narrativeId, headline }),
      });
      const spikeBody: unknown = await spikeRes.json();
      if (!spikeRes.ok) {
        throw new Error(
          spikeBody && typeof spikeBody === "object" && "error" in spikeBody
            ? String((spikeBody as { error: unknown }).error)
            : "could not start the piece",
        );
      }
      const spikeId = (spikeBody as { id: string }).id;

      const query = voice ? `?voice=${encodeURIComponent(voice)}` : "";
      router.push(`/spikes/${spikeId}${query}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "could not start the piece");
      setSubmitting(false);
    }
  }

  return (
    <section className="flex flex-col gap-4">
      <div>
        <h1 className="font-serif text-3xl font-semibold">Start a piece from my own idea</h1>
        <p className="max-w-2xl text-sm text-muted-foreground">
          For when you already know what you want to write. This skips the Radar&rsquo;s ranking
          run and the ranked-spikes review table entirely and goes straight to creating the piece
          and kicking off its interview. Looking to rank an idea against real source material
          instead?{" "}
          <Link href="/narrative" className="underline">
            Run the Radar
          </Link>
          .
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-xl">Your idea</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <Field label="Working title" htmlFor="new-piece-headline">
            <Input
              id="new-piece-headline"
              placeholder="e.g. Why single-vendor infra is a hidden risk"
              value={headline}
              onChange={(e) => setHeadline(e.target.value)}
            />
          </Field>
          <Field label="Your narrative" htmlFor="new-piece-seed-text">
            <TextArea
              id="new-piece-seed-text"
              placeholder="Say what you want to write about, in your own words…"
              value={seedText}
              onChange={(e) => setSeedText(e.target.value)}
            />
          </Field>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Audience" htmlFor="new-piece-audience">
              <Input
                id="new-piece-audience"
                placeholder="e.g. technical leaders on AWS"
                value={audience}
                onChange={(e) => setAudience(e.target.value)}
              />
            </Field>
            <Field label="Angle intent" htmlFor="new-piece-angle">
              <TextArea
                id="new-piece-angle"
                placeholder="e.g. reframe where the money leaks"
                value={angle}
                onChange={(e) => setAngle(e.target.value)}
              />
            </Field>
          </div>
          {voices.length === 0 ? (
            // Unified root-cause banner instead of an isolated "no voices available" option
            // (cmw-boss-facing-presentation, CRITICAL).
            <BrainUnavailableBanner subject="The voice list" />
          ) : (
            <Field label="Voice" htmlFor="new-piece-voice">
              <NativeSelect
                id="new-piece-voice"
                value={voice}
                onChange={(e) => setVoice(e.target.value)}
              >
                {voices.map((v) => (
                  <option key={v} value={v}>
                    {v}
                  </option>
                ))}
              </NativeSelect>
            </Field>
          )}
          <p className="text-xs text-muted-foreground">
            Attributed to you ({authorEmail}). This still creates a Spike — the origin the draft
            step reads to keep the piece on-subject — it just skips the ranking run and the
            ranked-spikes table.
          </p>
          {error ? <Alert>{error}</Alert> : null}
          <Button onClick={handleSubmit} disabled={!canSubmit}>
            {submitting ? "Starting…" : "Start piece"}
          </Button>
        </CardContent>
      </Card>
    </section>
  );
}
