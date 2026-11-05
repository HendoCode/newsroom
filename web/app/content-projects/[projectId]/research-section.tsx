"use client";

import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { relativeTime } from "@/lib/format/relative-time";
import type { ResearchGateView } from "@/lib/content-workflow/types";

/**
 * The project's research requirement, surfaced (research-v1): a sourced research report is
 * required by default after idea selection and before interviews. An operator with
 * subject-matter experience can record an experiential waiver instead — recorded with their
 * identity and a reason, never silently.
 */
interface Props {
  projectId: string;
  research: ResearchGateView;
  /** The project's version at render time — the waiver command is optimistic-concurrency
   * checked against it server-side. */
  projectVersion: number;
  email: string;
  onChanged: () => void;
}

interface FactRow {
  statement: string;
  source: string;
}

interface OpinionRow {
  statement: string;
}

export function ResearchSection({ projectId, research, projectVersion, email, onChanged }: Props) {
  const [reportFormOpen, setReportFormOpen] = useState(!research.satisfied);
  const [waiverFormOpen, setWaiverFormOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [subject, setSubject] = useState("");
  const [facts, setFacts] = useState<FactRow[]>([{ statement: "", source: "" }]);
  const [opinions, setOpinions] = useState<OpinionRow[]>([]);
  const [openQuestions, setOpenQuestions] = useState<string[]>([]);
  const [waiverReason, setWaiverReason] = useState("");

  // One clock for the relative-time display, captured on mount (lib/format/relative-time.ts's
  // documented convention).
  const clock = useMemo(() => new Date(), []);

  async function submitReport(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/content-workflow/${projectId}/research-report`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          subject,
          facts: facts
            .map((f) => ({ statement: f.statement.trim(), source: f.source.trim() }))
            .filter((f) => f.statement && f.source),
          opinions: opinions
            .map((o) => ({ statement: o.statement.trim() }))
            .filter((o) => o.statement),
          open_questions: openQuestions.map((q) => q.trim()).filter((q) => q),
          submitted_by: { subject_id: email, email },
        }),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(extractError(json) ?? "Could not save the research report.");
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "unknown");
      setBusy(false);
    }
  }

  async function submitWaiver(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const actor = { subject_id: email, email };
      const res = await fetch("/api/content-workflow/submit", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          schema_version: 1,
          command_type: "record-experiential-waiver",
          aggregate: { kind: "content-project", id: projectId },
          actor,
          idempotency_key: `waiver-${projectId}-${Date.now()}`,
          expected_version: projectVersion,
          payload: {
            type: "record-experiential-waiver",
            content_project_id: projectId,
            reason: waiverReason.trim(),
          },
        }),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(extractError(json) ?? "Could not record the waiver.");
      if (json.outcome === "rejected") {
        throw new Error(json.rejection?.message ?? "The waiver was rejected.");
      }
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "unknown");
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Research</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        {research.satisfied_by === "research-report" && research.report ? (
          <ReportView report={research.report} clock={clock} />
        ) : research.satisfied_by === "experiential-waiver" && research.waiver ? (
          <WaiverView waiver={research.waiver} clock={clock} />
        ) : (
          <p className="text-muted-foreground">
            A sourced research report is required before interviews can open. Add one below — or,
            if you have hands-on experience with this subject, record an experiential waiver
            instead.
          </p>
        )}

        {research.satisfied ? (
          <div className="space-y-2">
            {!reportFormOpen && (
              <Button variant="secondary" onClick={() => setReportFormOpen(true)}>
                {research.satisfied_by === "research-report"
                  ? "Add an updated report"
                  : "Add a research report"}
              </Button>
            )}
          </div>
        ) : (
          <div className="flex flex-wrap gap-2">
            {!reportFormOpen && (
              <Button variant="secondary" onClick={() => setReportFormOpen(true)}>
                Add a research report
              </Button>
            )}
            {!waiverFormOpen && (
              <Button variant="secondary" onClick={() => setWaiverFormOpen(true)}>
                Record an experiential waiver
              </Button>
            )}
          </div>
        )}

        {reportFormOpen && (
          <form onSubmit={submitReport} className="space-y-3 rounded border p-3">
            <h3 className="font-medium">Research report</h3>
            <Input
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              placeholder="What was researched"
              required
            />
            <div className="space-y-2">
              <span className="text-muted-foreground">Facts (each with its source)</span>
              {facts.map((fact, i) => (
                <div key={i} className="flex gap-2">
                  <Input
                    value={fact.statement}
                    onChange={(e) =>
                      setFacts(facts.map((f, j) => (j === i ? { ...f, statement: e.target.value } : f)))
                    }
                    placeholder="Fact"
                    required={i === 0}
                  />
                  <Input
                    value={fact.source}
                    onChange={(e) =>
                      setFacts(facts.map((f, j) => (j === i ? { ...f, source: e.target.value } : f)))
                    }
                    placeholder="Source"
                    required={i === 0}
                  />
                </div>
              ))}
              <Button
                type="button"
                variant="secondary"
                onClick={() => setFacts([...facts, { statement: "", source: "" }])}
              >
                Add a fact
              </Button>
            </div>
            <div className="space-y-2">
              <span className="text-muted-foreground">Opinions (kept apart from facts)</span>
              {opinions.map((opinion, i) => (
                <div key={i} className="flex gap-2">
                  <Input
                    value={opinion.statement}
                    onChange={(e) =>
                      setOpinions(
                        opinions.map((o, j) => (j === i ? { statement: e.target.value } : o)),
                      )
                    }
                    placeholder="Opinion"
                  />
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={() => setOpinions(opinions.filter((_, j) => j !== i))}
                  >
                    Remove
                  </Button>
                </div>
              ))}
              <Button
                type="button"
                variant="secondary"
                onClick={() => setOpinions([...opinions, { statement: "" }])}
              >
                Add an opinion
              </Button>
            </div>
            <div className="space-y-2">
              <span className="text-muted-foreground">Open questions (carried into interviews)</span>
              {openQuestions.map((question, i) => (
                <div key={i} className="flex gap-2">
                  <Input
                    value={question}
                    onChange={(e) =>
                      setOpenQuestions(openQuestions.map((q, j) => (j === i ? e.target.value : q)))
                    }
                    placeholder="Open question"
                  />
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={() => setOpenQuestions(openQuestions.filter((_, j) => j !== i))}
                  >
                    Remove
                  </Button>
                </div>
              ))}
              <Button
                type="button"
                variant="secondary"
                onClick={() => setOpenQuestions([...openQuestions, ""])}
              >
                Add an open question
              </Button>
            </div>
            <div className="flex items-center gap-2">
              <Button type="submit" disabled={busy}>
                {busy ? "Saving…" : "Save research report"}
              </Button>
              <Button type="button" variant="secondary" onClick={() => setReportFormOpen(false)}>
                Cancel
              </Button>
            </div>
          </form>
        )}

        {waiverFormOpen && !research.satisfied && (
          <form onSubmit={submitWaiver} className="space-y-3 rounded border p-3">
            <h3 className="font-medium">Experiential waiver</h3>
            <p className="text-muted-foreground">
              Skip the research report because you have direct experience with this subject. Your
              identity and reason are recorded with the waiver.
            </p>
            <textarea
              value={waiverReason}
              onChange={(e) => setWaiverReason(e.target.value)}
              placeholder="Why your experience covers this subject"
              className="w-full rounded border p-2"
              required
            />
            <div className="flex items-center gap-2">
              <Button type="submit" disabled={busy}>
                {busy ? "Recording…" : "Record waiver"}
              </Button>
              <Button type="button" variant="secondary" onClick={() => setWaiverFormOpen(false)}>
                Cancel
              </Button>
            </div>
          </form>
        )}

        {error && <p className="text-destructive">{error}</p>}
      </CardContent>
    </Card>
  );
}

function ReportView({
  report,
  clock,
}: {
  report: NonNullable<ResearchGateView["report"]>;
  clock: Date;
}) {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-2">
        <span className="font-medium">{report.subject}</span>
        {report.created_at && (
          <span className="text-xs text-muted-foreground">
            recorded {relativeTime(report.created_at, clock)}
          </span>
        )}
      </div>
      <div>
        <span className="text-muted-foreground">Facts</span>
        <ul className="mt-1 list-disc pl-5">
          {report.facts.map((fact, i) => (
            <li key={i}>
              {fact.statement} <span className="text-muted-foreground">— {fact.source}</span>
            </li>
          ))}
        </ul>
      </div>
      {report.opinions.length > 0 && (
        <div>
          <span className="text-muted-foreground">Opinions</span>
          <ul className="mt-1 list-disc pl-5">
            {report.opinions.map((opinion, i) => (
              <li key={i}>
                {opinion.statement}
                {opinion.holder ? (
                  <span className="text-muted-foreground"> — {opinion.holder}</span>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      )}
      {report.open_questions.length > 0 && (
        <div>
          <span className="text-muted-foreground">Open questions</span>
          <ul className="mt-1 list-disc pl-5">
            {report.open_questions.map((question, i) => (
              <li key={i}>{question}</li>
            ))}
          </ul>
        </div>
      )}
      <p className="text-xs text-muted-foreground">
        A new report supersedes this one; history is kept.
      </p>
    </div>
  );
}

function WaiverView({
  waiver,
  clock,
}: {
  waiver: NonNullable<ResearchGateView["waiver"]>;
  clock: Date;
}) {
  return (
    <div className="space-y-1">
      <p className="font-medium">Experiential waiver recorded</p>
      <p>
        {waiver.actor.email ?? waiver.actor.subject_id}: {waiver.reason}
      </p>
      <p className="text-xs text-muted-foreground">
        recorded {relativeTime(waiver.recorded_at, clock)}
      </p>
    </div>
  );
}

function extractError(json: unknown): string | null {
  if (typeof json !== "object" || json === null) return null;
  const record = json as Record<string, unknown>;
  if (typeof record.error === "string") return record.error;
  if (typeof record.detail === "string") return record.detail;
  if (Array.isArray(record.detail) && record.detail.length > 0) {
    const first = record.detail[0] as { msg?: string };
    if (first.msg) return first.msg;
  }
  return null;
}
