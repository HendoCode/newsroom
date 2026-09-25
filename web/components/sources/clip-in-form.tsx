"use client";

import * as React from "react";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/form-controls";
import { Input } from "@/components/ui/input";
import { TextArea } from "@/components/ui/textarea";
import type { ClipInResponse } from "@/lib/sources/types";

function todayIso(now: Date): string {
  return now.toISOString().slice(0, 10);
}

/**
 * The credential-free LinkedIn/X clip-in form (D8; cmw-ui-wireframes screen 7): paste text/URL +
 * source person/account + date + tags → straight to the content lake, `read-as-needed`. There is
 * no fetch, no scraper, and nothing to authenticate — the only sanctioned LinkedIn/X path.
 */
export function ClipInForm({
  clipSourceId,
  now,
  onSetupSource,
}: {
  clipSourceId: string | null;
  now: Date;
  /** Jump to the source-setup panel with "LinkedIn / X (clip-in)" preselected — the one-time step
   * this form needs before it can be used at all. Omit if there's nowhere to jump to. */
  onSetupSource?: () => void;
}) {
  const [content, setContent] = React.useState("");
  const [author, setAuthor] = React.useState("");
  const [date, setDate] = React.useState(todayIso(now));
  const [tags, setTags] = React.useState("");
  const [submitting, setSubmitting] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [success, setSuccess] = React.useState<ClipInResponse | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!clipSourceId) return;
    setSubmitting(true);
    setError(null);
    setSuccess(null);
    try {
      const res = await fetch("/api/connectors/clip", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          source_id: clipSourceId,
          content,
          author: author || null,
          content_date: date || null,
          tags: tags
            .split(",")
            .map((t) => t.trim())
            .filter(Boolean),
        }),
      });
      const body = (await res.json()) as ClipInResponse | { error: string };
      if (!res.ok) throw new Error("error" in body ? body.error : "clip-in failed");
      setSuccess(body as ClipInResponse);
      setContent("");
      setAuthor("");
      setTags("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "clip-in failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2 text-lg">
          Clip in from LinkedIn / X
          <Badge variant="muted">read-as-needed · credential-free</Badge>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <p className="mb-3 text-sm text-muted-foreground">
          No clean legitimate read path for these, so a human pastes the material. It goes straight
          into the content lake with the minimal metadata that can&rsquo;t be inferred.
        </p>

        {!clipSourceId ? (
          <div className="flex flex-col items-start gap-2 rounded-md border border-dashed bg-muted/30 px-3 py-2 text-sm text-muted-foreground">
            <p>
              No LinkedIn / X clip-in source is set up yet — clips need one to attribute to. This
              is a one-time step, separate from pasting a clip.
            </p>
            {onSetupSource ? (
              <Button type="button" variant="outline" size="sm" onClick={onSetupSource}>
                Set up a clip-in source
              </Button>
            ) : null}
          </div>
        ) : (
          <form className="flex flex-col gap-4" onSubmit={handleSubmit}>
            <Field label="Paste text or URL" htmlFor="clip-content">
              <TextArea
                id="clip-content"
                value={content}
                onChange={(e) => setContent(e.target.value)}
                placeholder="Paste the post / thread text (or a URL to reference)"
                required
              />
            </Field>

            <div className="grid grid-cols-2 gap-4">
              <Field label="Source person / account" htmlFor="clip-author">
                <Input
                  id="clip-author"
                  value={author}
                  onChange={(e) => setAuthor(e.target.value)}
                  placeholder="@handle or name"
                />
              </Field>
              <Field label="Date" htmlFor="clip-date">
                <Input
                  id="clip-date"
                  type="date"
                  value={date}
                  onChange={(e) => setDate(e.target.value)}
                />
              </Field>
            </div>

            <Field label="Tags (optional)" htmlFor="clip-tags">
              <Input
                id="clip-tags"
                value={tags}
                onChange={(e) => setTags(e.target.value)}
                placeholder="genai, pricing, aws"
              />
            </Field>

            {error ? <Alert>{error}</Alert> : null}
            {success ? (
              <p className="text-sm text-primary" role="status">
                Clip added to the content lake.
              </p>
            ) : null}

            <div>
              <Button type="submit" disabled={submitting || !content.trim()}>
                {submitting ? "Adding…" : "Add clip to content lake"}
              </Button>
            </div>

            <p className="text-xs text-muted-foreground">
              A bookmarklet is explicitly deferred (§9) — v1 stays manual. Clips are
              read-as-needed; the Radar never auto-harvests LinkedIn/X.
            </p>
          </form>
        )}
      </CardContent>
    </Card>
  );
}
