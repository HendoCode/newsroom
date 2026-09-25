"use client";

import * as React from "react";
import Link from "next/link";
import { Loader2 } from "lucide-react";

import { BrainUnavailableBanner } from "@/components/brain/brain-unavailable-banner";
import { SpikesTable } from "@/components/spikes/spikes-table";
import { Field, NativeSelect } from "@/components/ui/form-controls";
import { Input } from "@/components/ui/input";
import { TextArea } from "@/components/ui/textarea";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { sortByConvergence } from "@/lib/spikes/filters";
import type { Spike, SpikeListResponse } from "@/lib/spikes/types";
import type { OracleEntryMode, OracleRunResult } from "@/lib/oracle/types";
import { cn } from "@/lib/utils";

/**
 * Narrative → Oracle entry (use case B; cmw-ui-wireframes screen 8): two entry cards (A/B), the
 * narrative composer (audience/angle intent), the Oracle run panel (voice/lookback), and a
 * last-run ranked-spikes preview. One on-demand Oracle, two entry points (D7) — Entry B first
 * creates a Narrative (the audience/angle seed), then runs the Oracle against it; Entry A runs
 * straight, no seed.
 */
export function NarrativeOracle({
  voices,
  authorEmail,
  initialVoice = "",
}: {
  voices: string[];
  authorEmail: string;
  initialVoice?: string;
}) {
  const [entryMode, setEntryMode] = React.useState<OracleEntryMode>("narrative");
  const [voice, setVoice] = React.useState(() => {
    // Priority: initialVoice (from URL param), then localStorage, then first voice.
    if (initialVoice && voices.includes(initialVoice)) {
      return initialVoice;
    }
    if (typeof window !== "undefined") {
      const saved = window.localStorage.getItem("radar_last_voice");
      if (saved && voices.includes(saved)) {
        return saved;
      }
    }
    return voices[0] ?? "";
  });

  React.useEffect(() => {
    if (voice && typeof window !== "undefined") {
      window.localStorage.setItem("radar_last_voice", voice);
    }
  }, [voice]);
  const [lookbackDays, setLookbackDays] = React.useState(7);
  const [seedText, setSeedText] = React.useState("");
  const [audience, setAudience] = React.useState("");
  const [angle, setAngle] = React.useState("");
  const [running, setRunning] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [lastResult, setLastResult] = React.useState<OracleRunResult | null>(null);
  const [rankedSpikes, setRankedSpikes] = React.useState<Spike[] | null>(null);

  const canRun = voice !== "" && (entryMode === "open-scan" || seedText.trim() !== "") && !running;

  async function handleRun() {
    setRunning(true);
    setError(null);
    try {
      let narrativeId: string | null = null;
      if (entryMode === "narrative") {
        const narrativeRes = await fetch("/api/narratives", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            seed_text: seedText,
            audience: audience || null,
            angle: angle || null,
          }),
        });
        const narrativeBody = await narrativeRes.json();
        if (!narrativeRes.ok) throw new Error(narrativeBody.error ?? "narrative failed");
        narrativeId = narrativeBody.id as string;
      }

      const runRes = await fetch("/api/oracle/run", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          entry_mode: entryMode,
          voice,
          lookback_days: lookbackDays,
          narrative_id: narrativeId,
        }),
      });
      const runBody: unknown = await runRes.json();
      if (!runRes.ok) {
        const message =
          runBody && typeof runBody === "object" && "error" in runBody
            ? String((runBody as { error: unknown }).error)
            : "radar run failed";
        throw new Error(message);
      }
      const result = runBody as OracleRunResult;
      setLastResult(result);

      const spikesRes = await fetch(`/api/spikes?origin_ref=${result.job_id}&origin_kind=oracle-run`, { cache: "no-store" });
      if (spikesRes.ok) {
        const spikesBody = (await spikesRes.json()) as SpikeListResponse;
        setRankedSpikes(sortByConvergence(spikesBody.items));
      } else {
        setRankedSpikes([]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "radar run failed");
    } finally {
      setRunning(false);
    }
  }

  return (
    <section className="flex flex-col gap-4">
      <div>
        <h1 className="font-serif text-3xl font-semibold">Run the Radar</h1>
        <p className="max-w-2xl text-sm text-muted-foreground">
          The Radar scans the content lake over a lookback window and returns ranked candidate
          topics (spikes). One on-demand Radar, two entry points.
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <button
          type="button"
          onClick={() => setEntryMode("narrative")}
          aria-pressed={entryMode === "narrative"}
          className={cn(
            "rounded-lg border p-4 text-left transition-colors",
            entryMode === "narrative" ? "border-2 border-primary" : "border-border",
          )}
        >
          <Badge variant="secondary">Entry B — narrative-biased</Badge>
          <h2 className="mt-2 font-serif text-lg font-semibold">Speak a narrative</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Say what you want to write about, in your own voice, with audience/angle intent. That
            intent biases ranking (a soft bias, not a hard filter) and is captured for later
            (distribution, §9).
          </p>
        </button>
        <button
          type="button"
          onClick={() => setEntryMode("open-scan")}
          aria-pressed={entryMode === "open-scan"}
          className={cn(
            "rounded-lg border p-4 text-left transition-colors",
            entryMode === "open-scan" ? "border-2 border-primary" : "border-border",
          )}
        >
          <Badge variant="muted">Entry A — open scan</Badge>
          <h2 className="mt-2 font-serif text-lg font-semibold">Open scan</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            No seed. Pure convergence ranking over the window — surfaces whatever is converging in
            the sources right now.
          </p>
        </button>
      </div>

      <div className="grid gap-4 lg:grid-cols-[1fr,320px]">
        <Card>
          <CardHeader>
            <CardTitle className="text-xl">Your narrative</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <TextArea
              aria-label="Narrative"
              placeholder="e.g. 'S3 is maligned as the most expensive storage on earth, but with the crazy cost of mis-applied GenAI, S3 costs are irrelevant — yes, the basics still matter…'"
              value={seedText}
              onChange={(e) => setSeedText(e.target.value)}
              disabled={entryMode === "open-scan"}
            />
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Audience" htmlFor="audience">
                <Input
                  id="audience"
                  placeholder="e.g. technical leaders on AWS"
                  value={audience}
                  onChange={(e) => setAudience(e.target.value)}
                  disabled={entryMode === "open-scan"}
                />
              </Field>
              <Field label="Angle intent" htmlFor="angle">
                <TextArea
                  id="angle"
                  placeholder="e.g. reframe where the money leaks"
                  value={angle}
                  onChange={(e) => setAngle(e.target.value)}
                  disabled={entryMode === "open-scan"}
                />
              </Field>
            </div>
            <p className="text-xs text-muted-foreground">
              The narrative is attributed to you ({authorEmail}) and becomes the origin of any
              spikes it produces. Audience/angle intent is stored on the spike and travels with
              the piece.
            </p>
          </CardContent>
        </Card>

        <div className="flex flex-col gap-3">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Radar run</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              {voices.length === 0 ? (
                // Unified root-cause banner instead of an isolated "no voices available" option
                // (cmw-boss-facing-presentation, CRITICAL).
                <BrainUnavailableBanner subject="The voice list" />
              ) : (
                <Field label="Voice" htmlFor="voice">
                  <NativeSelect id="voice" value={voice} onChange={(e) => setVoice(e.target.value)}>
                    {voices.map((v) => (
                      <option key={v} value={v}>
                        {v}
                      </option>
                    ))}
                  </NativeSelect>
                </Field>
              )}
              <Field label="Lookback window (this run)" htmlFor="lookback">
                <div className="flex items-center gap-1">
                  <Input
                    id="lookback"
                    type="number"
                    min={1}
                    max={365}
                    className="w-20"
                    value={lookbackDays}
                    onChange={(e) => setLookbackDays(Number(e.target.value) || 7)}
                  />
                  <span className="text-sm text-muted-foreground">days</span>
                </div>
              </Field>
              <p className="text-xs text-muted-foreground">
                Sources in scope:{" "}
                <Link href="/sources" className="underline">
                  manage sources
                </Link>
                . Cost is a courtesy readout reported after the run completes — it never blocks
                (D14).
              </p>
              <Button onClick={handleRun} disabled={!canRun} className="w-full">
                {running ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : null}
                {running ? "Running…" : "Run Radar"}
              </Button>
              {running ? (
                <p role="status" className="text-xs text-muted-foreground">
                  Radar running — the Oracle job runs to completion on this call; the ranked list
                  appears below when it flips to done.
                </p>
              ) : (
                <p className="text-xs text-muted-foreground">
                  Runs as a background job; you&rsquo;ll see the ranked list below once it flips to
                  done.
                </p>
              )}
            </CardContent>
          </Card>

          {error ? <Alert>{error}</Alert> : null}

          {lastResult ? (
            <p
              role="status"
              className={cn(
                "rounded-md border px-3 py-2 text-sm",
                lastResult.status === "succeeded"
                  ? "border-success/40 bg-success/10 text-success"
                  : lastResult.status === "failed"
                    ? "border-destructive/40 bg-destructive/10 text-destructive"
                    : "bg-muted/40 text-muted-foreground",
              )}
            >
              {lastResult.status === "succeeded"
                ? `Radar run complete — job ${lastResult.job_id.slice(0, 8)}`
                : lastResult.status === "failed"
                  ? `Radar run failed — job ${lastResult.job_id.slice(0, 8)}`
                  : `Job ${lastResult.job_id.slice(0, 8)} — ${lastResult.status}`}
              {lastResult.cost_usd ? ` · $${lastResult.cost_usd.toFixed(2)}` : null}
              {lastResult.error ? ` — ${lastResult.error}` : null}
            </p>
          ) : null}
        </div>
      </div>

      {rankedSpikes !== null && (
        <Card>
          <CardHeader>
            <CardTitle className="text-xl">Last run — ranked spikes</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-2">
            {rankedSpikes.length === 0 ? (
              <p className="py-4 text-sm text-muted-foreground">
                No spikes produced by this run. The content lake may be empty.
              </p>
            ) : (
              <SpikesTable
                spikes={rankedSpikes}
                selectedId={null}
                onSelect={() => {}}
                voiceHint={voice}
              />
            )}
            <p className="text-xs text-muted-foreground">
              Unpicked spikes are auto-saved to the{' '}
              <Link href="/spikes" className="underline">
                Vault
              </Link>
              .
            </p>
          </CardContent>
        </Card>
      )}
    </section>
  );
}
