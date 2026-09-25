"use client";

import * as React from "react";
import Link from "next/link";

import { SpikeStatusBadge } from "@/components/dashboard/stage-badge";
import { BrainUnavailableBanner } from "@/components/brain/brain-unavailable-banner";
import { NarrativeReveal } from "@/components/spikes/narrative-reveal";
import { Field, NativeSelect } from "@/components/ui/form-controls";
import { Input } from "@/components/ui/input";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { convergenceLabel } from "@/lib/spikes/format";
import { defaultInterviewerSelection, slugifyHeadline } from "@/lib/spikes/kickoff";
import { originNarrativeId } from "@/lib/spikes/origin";
import type { PickSpikeResponse, Spike } from "@/lib/spikes/types";
import type { Interview } from "@/lib/interviews/types";
import type { InterviewRecord, PieceDetail } from "@/lib/pieces/types";

async function readErrorMessage(res: Response, fallback: string): Promise<string> {
  const body: unknown = await res.json().catch(() => null);
  if (body && typeof body === "object" && "error" in body) {
    return String((body as { error: unknown }).error);
  }
  return fallback;
}

/**
 * Spike → kickoff (use case C; cmw-ui-wireframes screen 6): a 5-step stepper — spike picked,
 * create the piece, assign the expert, the agent's pre-selected interviewer personas (editable),
 * and a shareable interview link (Slack/copy — a plain link into the assigned interview under the
 * simple identity login, not an OAuth-specific deep link). Ownership is attribution, not a lock
 * (D15): the spike's own creator/origin never changes here.
 */
export function SpikeKickoff({
  spike: initialSpike,
  voices,
  personas,
  radarVoice,
}: {
  spike: Spike;
  voices: string[];
  personas: string[];
  /** The Voice already chosen on the Run-the-Radar form that produced this spike, if any —
   * carried over as the default here instead of silently resetting to `voices[0]` (cmw-first-run-ux-batch item 7). */
  radarVoice?: string | null;
}) {
  const [spike, setSpike] = React.useState(initialSpike);
  const [pieceId, setPieceId] = React.useState<string | null>(initialSpike.piece_id);
  // Whether `pieceId` names a piece that already existed when this screen loaded (a revisit) or
  // one this screen just created itself — distinguishes "resuming an already-open interview" from
  // "the interview we just opened atomically with the piece" (cmw-piece-interviewing-without-interview).
  const initialPieceIdRef = React.useRef(initialSpike.piece_id);
  const [slug, setSlug] = React.useState(slugifyHeadline(initialSpike.headline));
  const [voice, setVoice] = React.useState(
    radarVoice && voices.includes(radarVoice) ? radarVoice : voices[0] ?? "",
  );
  const [target, setTarget] = React.useState(
    [initialSpike.intent?.audience, initialSpike.intent?.angle].filter(Boolean).join(" — "),
  );
  const [creatingPiece, setCreatingPiece] = React.useState(false);
  const [createPieceError, setCreatePieceError] = React.useState<string | null>(null);

  const [expert, setExpert] = React.useState("");
  const [about, setAbout] = React.useState(initialSpike.headline);
  const [selectedPersonas, setSelectedPersonas] = React.useState<string[]>(() =>
    defaultInterviewerSelection(personas),
  );

  const [interview, setInterview] = React.useState<Interview | null>(null);
  const [resumedInterview, setResumedInterview] = React.useState(false);
  const [checkingExistingInterview, setCheckingExistingInterview] = React.useState(false);
  const [existingInterviewCheckError, setExistingInterviewCheckError] = React.useState<
    string | null
  >(null);
  const [openingInterview, setOpeningInterview] = React.useState(false);
  const [openInterviewError, setOpenInterviewError] = React.useState<string | null>(null);
  const [copyStatus, setCopyStatus] = React.useState<string | null>(null);
  const [origin, setOrigin] = React.useState("");

  React.useEffect(() => {
    setOrigin(window.location.origin);
  }, []);

  // Once a piece exists — whether from a prior visit (e.g. pressing the dashboard's kickoff
  // action a second time) or from `handleCreatePiece` just below, which now opens the Interview
  // atomically with the Piece (cmw-piece-interviewing-without-interview) — pick it up here rather
  // than ever offering a fresh "Generate link" before checking. That check is what used to be
  // missing, and pressing it twice forked the interview history instead of resuming it (see
  // AGENTS.md). `isRevisit` only affects the "resuming" copy below, not the fetch itself: a piece
  // that already existed at page-load gets "resuming"; one this screen just created doesn't.
  React.useEffect(() => {
    if (!pieceId) return;
    const isRevisit = pieceId === initialPieceIdRef.current;
    let active = true;
    setCheckingExistingInterview(true);
    setExistingInterviewCheckError(null);
    (async () => {
      try {
        const pieceRes = await fetch(`/api/pieces/${encodeURIComponent(pieceId)}`);
        if (!pieceRes?.ok) {
          throw new Error("could not check for an existing interview");
        }
        const detail = (await pieceRes.json()) as PieceDetail;
        const open = detail.interviews.find(
          (i: InterviewRecord) => i.status === "open",
        );
        if (!open || !active) return;
        const interviewRes = await fetch(
          `/api/interviews/${encodeURIComponent(open.interview_id)}`,
        );
        if (!interviewRes?.ok) {
          throw new Error("could not load the already-open interview");
        }
        const full = (await interviewRes.json()) as Interview;
        if (!active) return;
        setInterview(full);
        setResumedInterview(isRevisit);
        setExpert(full.assigned_expert ?? "");
        setAbout(full.about ?? "");
        setSelectedPersonas(full.interviewer_personas);
      } catch (err) {
        if (active) {
          setExistingInterviewCheckError(
            err instanceof Error ? err.message : "could not check for an existing interview",
          );
        }
      } finally {
        if (active) setCheckingExistingInterview(false);
      }
    })();
    return () => {
      active = false;
    };
  }, [pieceId]);

  const pieceCreated = pieceId != null;
  const shareLink = interview ? `${origin}/interviews/${interview.id}` : null;
  const narrativeId = originNarrativeId(spike);

  function togglePersona(name: string) {
    setSelectedPersonas((prev) =>
      prev.includes(name) ? prev.filter((p) => p !== name) : [...prev, name],
    );
  }

  async function handleCreatePiece() {
    setCreatingPiece(true);
    setCreatePieceError(null);
    try {
      const res = await fetch(`/api/spikes/${spike.id}/pick`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          voice,
          slug: slug || undefined,
          target: target || undefined,
          // Opens the first Interview atomically with the Piece (cmw-piece-interviewing-without-interview)
          // — whatever expert/personas are set below at the moment of creation. There is no longer
          // a separate "generate link" step for a freshly created piece: that gap between piece
          // creation and interview creation is exactly what left pieces stuck at `interviewing`
          // with nothing to conduct.
          interviewer_personas: selectedPersonas,
          assigned_expert: expert || undefined,
          about: about || undefined,
        }),
      });
      const body: unknown = await res.json();
      if (!res.ok) {
        throw new Error(
          body && typeof body === "object" && "error" in body
            ? String((body as { error: unknown }).error)
            : "could not create piece",
        );
      }
      const result = body as PickSpikeResponse;
      setPieceId(result.piece_id);
      setSlug(result.slug);
      setSpike(result.spike);
    } catch (err) {
      setCreatePieceError(err instanceof Error ? err.message : "could not create piece");
    } finally {
      setCreatingPiece(false);
    }
  }

  async function handleGenerateLink() {
    if (!pieceId) return;
    setOpeningInterview(true);
    setOpenInterviewError(null);
    try {
      const res = await fetch(`/api/pieces/${pieceId}/interviews`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          interviewer_personas: selectedPersonas,
          assigned_expert: expert || null,
          about: about || null,
        }),
      });
      if (!res.ok) {
        throw new Error(await readErrorMessage(res, "could not open interview"));
      }
      const created = (await res.json()) as Interview;
      setInterview(created);
    } catch (err) {
      setOpenInterviewError(err instanceof Error ? err.message : "could not open interview");
    } finally {
      setOpeningInterview(false);
    }
  }

  async function copyToClipboard(text: string, label: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopyStatus(`${label} copied`);
    } catch {
      setCopyStatus(`Couldn't copy automatically — copy manually: ${text}`);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <Button asChild variant="ghost" size="sm" className="self-start">
        <Link href="/spikes">← Back to Spikes &amp; Vault</Link>
      </Button>

      <div className="grid gap-4 lg:grid-cols-[1fr,320px]">
        <div className="flex flex-col gap-4">
          {/* Step 1 */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-lg">
                <StepNumber n={1} />
                Spike picked
              </CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-2">
              <div className="flex items-center justify-between gap-3 rounded-md border bg-muted/30 px-3 py-2">
                <div>
                  <div className="font-medium">{spike.headline}</div>
                  <div className="text-xs text-muted-foreground">
                    convergence <b>{convergenceLabel(spike.convergence_score)}</b> · maps to{" "}
                    <b>{spike.customer_partner ?? "none yet"}</b> ·{" "}
                    <b>attributed to {spike.creator}</b> (stays, even if someone else picks it)
                  </div>
                </div>
                <SpikeStatusBadge status={spike.status} />
              </div>
              {narrativeId ? <NarrativeReveal narrativeId={narrativeId} /> : null}
              <p className="text-xs text-muted-foreground">
                Picking creates a piece at the interviewing stage.
                The spike keeps its original creator/origin attribution.
              </p>
            </CardContent>
          </Card>

          {/* Step 2 */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-lg">
                <StepNumber n={2} />
                Create the piece
              </CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              {pieceCreated ? (
                <Alert variant="success">
                  {checkingExistingInterview ? (
                    <>
                      Piece <b>{slug}</b> created (voice <b>{voice}</b>) — checking its interview…
                    </>
                  ) : interview ? (
                    <>
                      Piece <b>{slug}</b> created (voice <b>{voice}</b>) with its interview already
                      open — copy the share link in step 5 below, or{" "}
                    </>
                  ) : (
                    <>
                      Piece <b>{slug}</b> already exists (voice <b>{voice}</b>) but has no
                      interview yet — assign an expert and generate the interview link in steps
                      3-5 below, or{" "}
                    </>
                  )}
                  {checkingExistingInterview ? null : (
                    <>
                      <Link href={`/pieces/${pieceId}`} className="underline">
                        Open piece
                      </Link>{" "}
                      directly.
                    </>
                  )}
                </Alert>
              ) : (
                <>
                  <div className="grid gap-3 sm:grid-cols-2">
                    {voices.length === 0 ? (
                      // Unified root-cause banner instead of an isolated "no voices available"
                      // option (cmw-boss-facing-presentation, CRITICAL).
                      <div className="sm:col-span-2">
                        <BrainUnavailableBanner subject="The voice list" />
                      </div>
                    ) : (
                      <Field label="Voice (exactly one per piece)" htmlFor="kickoff-voice">
                        <NativeSelect
                          id="kickoff-voice"
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
                    <Field label="Slug" htmlFor="kickoff-slug">
                      <Input
                        id="kickoff-slug"
                        value={slug}
                        onChange={(e) => setSlug(e.target.value)}
                      />
                    </Field>
                  </div>
                  <Field label="Target / audience &amp; angle intent" htmlFor="kickoff-target">
                    <Input
                      id="kickoff-target"
                      value={target}
                      onChange={(e) => setTarget(e.target.value)}
                      placeholder="e.g. Reframe essay for technical leaders litigating cloud bills"
                    />
                  </Field>
                  {createPieceError ? <Alert>{createPieceError}</Alert> : null}
                  <Button
                    onClick={handleCreatePiece}
                    disabled={creatingPiece || voice === "" || selectedPersonas.length === 0}
                  >
                    {creatingPiece ? "Creating…" : "Create piece"}
                  </Button>
                  {selectedPersonas.length === 0 ? (
                    <p className="text-xs text-muted-foreground">
                      Select at least one interviewer persona in step 4 below — its Interview opens
                      together with the piece.
                    </p>
                  ) : null}
                </>
              )}
            </CardContent>
          </Card>

          {/* Step 3 */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-lg">
                <StepNumber n={3} />
                Assign the expert
              </CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              <p className="text-xs text-muted-foreground">
                Internal employees only in v1. Under the simple identity login there is no
                directory search yet — enter the expert&rsquo;s company email; they declare who
                they are when they open the link. Set this before creating the piece above — its
                Interview opens together with it, using whatever is set here at that moment.
              </p>
              <div className="grid gap-3 sm:grid-cols-2">
                <Field label="Assigned expert (email)" htmlFor="kickoff-expert">
                  <Input
                    id="kickoff-expert"
                    type="email"
                    value={expert}
                    onChange={(e) => setExpert(e.target.value)}
                    placeholder="demo-mira@company.com"
                    disabled={interview != null || checkingExistingInterview}
                  />
                </Field>
                <Field label="What it's about" htmlFor="kickoff-about">
                  <Input
                    id="kickoff-about"
                    value={about}
                    onChange={(e) => setAbout(e.target.value)}
                    disabled={interview != null || checkingExistingInterview}
                  />
                </Field>
              </div>
              <p className="text-xs text-muted-foreground">
                Multiple experts can be assigned over time; each gets their own interview that
                feeds the one piece.
              </p>
            </CardContent>
          </Card>

          {/* Step 4 */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-lg">
                <StepNumber n={4} />
                Interviewer set (pre-selected)
              </CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-2">
              <p className="text-xs text-muted-foreground">
                A small starting set is pre-selected below; edit freely before creating the piece
                above (or before generating the link, for a piece that already exists but has no
                interview yet).
              </p>
              <div className="flex flex-wrap gap-2">
                {personas.length === 0 ? (
                  // Same unified banner as the voice selector above — an empty persona roster is
                  // the same root cause, never its own isolated message.
                  <div className="w-full">
                    <BrainUnavailableBanner subject="The interviewer persona list" />
                  </div>
                ) : null}
                {personas.map((name) => {
                  const on = selectedPersonas.includes(name);
                  return (
                    <Button
                      key={name}
                      type="button"
                      size="sm"
                      variant={on ? "default" : "outline"}
                      disabled={interview != null || checkingExistingInterview}
                      onClick={() => togglePersona(name)}
                      aria-pressed={on}
                      className="h-auto rounded-full px-3 py-1 text-xs"
                    >
                      {name}
                    </Button>
                  );
                })}
              </div>
            </CardContent>
          </Card>

          {/* Step 5 */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-lg">
                <StepNumber n={5} />
                Share the link
              </CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              <p className="rounded-md border border-dashed bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
                <b className="text-foreground">Plain shareable link.</b> Opens the assigned
                interview under the simple identity login — anyone opening it declares who they
                are. Not an OAuth-specific deep link.
              </p>

              {!interview ? (
                <>
                  {existingInterviewCheckError ? (
                    <Alert>
                      {existingInterviewCheckError} — refresh the page before generating a new
                      link, so an already-open interview isn&rsquo;t forked into a second one.
                    </Alert>
                  ) : null}
                  {openInterviewError ? <Alert>{openInterviewError}</Alert> : null}
                  <Button
                    onClick={handleGenerateLink}
                    disabled={
                      !pieceCreated ||
                      openingInterview ||
                      checkingExistingInterview ||
                      existingInterviewCheckError != null ||
                      selectedPersonas.length === 0
                    }
                  >
                    {checkingExistingInterview
                      ? "Checking for an existing interview…"
                      : openingInterview
                        ? "Generating…"
                        : "Generate link"}
                  </Button>
                  {!pieceCreated ? (
                    <p className="text-xs text-muted-foreground">
                      Create the piece (step 2) before generating a link.
                    </p>
                  ) : null}
                </>
              ) : (
                <>
                  {resumedInterview ? (
                    <p role="status" className="text-xs text-muted-foreground">
                      An interview was already open for this piece — resuming it instead of
                      starting a new one.
                    </p>
                  ) : null}
                  <Input readOnly value={shareLink ?? ""} aria-label="Interview share link" />
                  <div className="flex flex-wrap gap-2">
                    <Button onClick={() => copyToClipboard(shareLink ?? "", "Link")}>
                      Copy link
                    </Button>
                    <Button
                      variant="outline"
                      onClick={() =>
                        copyToClipboard(
                          `Kicking off an interview for "${spike.headline}" — please open: ${shareLink ?? ""}`,
                          "Slack message",
                        )
                      }
                    >
                      Copy Slack message
                    </Button>
                  </div>
                  {copyStatus ? (
                    <p role="status" className="text-xs text-muted-foreground">
                      {copyStatus}
                    </p>
                  ) : null}
                </>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Summary */}
        <div className="flex flex-col gap-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Kickoff summary</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-1 text-sm text-muted-foreground">
              <div>
                Piece: <b className="text-foreground">{pieceCreated ? slug : "not yet created"}</b>
              </div>
              <div>
                Voice: <b className="text-foreground">{voice || "—"}</b>
              </div>
              <div>
                Expert: <b className="text-foreground">{expert || "not yet assigned"}</b>
              </div>
              <div>
                Personas:{" "}
                <b className="text-foreground">
                  {selectedPersonas.length > 0 ? selectedPersonas.join(", ") : "none selected"}
                </b>
              </div>
              <div>
                Stage on kickoff: <span className="font-mono">interviewing</span>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Not in v1</CardTitle>
            </CardHeader>
            <CardContent className="text-xs text-muted-foreground">
              No calendar/scheduling. No external (non-employee) interviewees.
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

function StepNumber({ n }: { n: number }) {
  return (
    <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary text-xs font-bold text-primary-foreground">
      {n}
    </span>
  );
}
