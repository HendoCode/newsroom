"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { RefreshCw } from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { SeededDataBadge } from "@/components/dashboard/seeded-data-badge";
import { Button } from "@/components/ui/button";
import { ClipInForm } from "@/components/sources/clip-in-form";
import { Field } from "@/components/ui/form-controls";
import { Input } from "@/components/ui/input";
import { SourceForm, type SourceFormValues } from "@/components/sources/source-form";
import { SourcesTable } from "@/components/sources/sources-table";
import type { RefreshResponse, Source, SourceKind, SourceListResponse } from "@/lib/sources/types";

/** The current form target: a blank "add" panel, or an existing source being edited. */
type FormTarget = "new" | Source;

/** Which single panel is showing below the table — never both at once (see `activePanel` below). */
type ActivePanel = "source" | "clip";

/**
 * The source registry (Item 6 / D8; cmw-ui-wireframes screen 7): manage what the Oracle reads.
 * Default lookback window + on-demand "Refresh sources now" + "+ Add source"; the sources table
 * (kind · classification · config · server-side credential · last refreshed · enable · edit); a
 * Green-connector add/edit panel; and the credential-free LinkedIn/X clip-in form.
 *
 * **The add/edit panel and the clip-in panel are mutually exclusive** (`activePanel`) — before
 * this they rendered side by side unconditionally, which read as "I might use either or both in
 * the same movement" with no signal about how they relate (Hendo, 2026-08-10, the third distinct
 * complaint about this screen after PR #83's vanishing-source and silent-save fixes). Two clearly
 * labeled toolbar buttons ("+ Add source" vs "Clip in a LinkedIn/X post") make the choice explicit
 * BEFORE either form renders, rather than merging them into one kind-aware form: registering a
 * source (a rare, admin-ish setup step) and pasting a clip (the frequent day-to-day action) are
 * genuinely different tasks that happen to share this screen, and collapsing them into one widget
 * would just relocate the ambiguity into a single form's own "kind" field. `SourceForm` still
 * supports the `linkedin-x-clip` kind (it's the only way to create/rename that registry entry),
 * with its own copy clarifying that picking it there only registers the *channel* — the empty
 * clip-in panel's "Set up a clip-in source" shortcut is the one guided path between the two.
 */
export function SourceRegistry({ initial }: { initial: SourceListResponse }) {
  const router = useRouter();
  const [sources, setSources] = React.useState<Source[]>(initial.items);
  const [dataSource, setDataSource] = React.useState<SourceListResponse["source"]>(initial.source);
  const [lookbackDays, setLookbackDays] = React.useState(7);
  const [refreshing, setRefreshing] = React.useState(false);
  const [refreshMessage, setRefreshMessage] = React.useState<string | null>(null);
  // Per-source errors from the LAST refresh — the connectors' refresh entrypoint deliberately
  // reports a bad source inline rather than as an HTTP error (warns, doesn't block, §5), but until
  // this the UI only ever showed an aggregate "(N warned)" count with no way to see which source
  // or why (cmw-first-run-ux-batch item 2). Keyed by source id; cleared at the start of each run.
  const [refreshErrors, setRefreshErrors] = React.useState<Record<string, string>>({});
  const [formTarget, setFormTarget] = React.useState<FormTarget>("new");
  // Which of the two panels is showing — never both (see the module docstring above).
  const [activePanel, setActivePanel] = React.useState<ActivePanel>("source");
  // Preselects SourceForm's Kind field on the next reset — only ever set by the clip-in panel's
  // "Set up a clip-in source" shortcut, so that jump lands on `linkedin-x-clip` instead of the
  // plain "gdrive" default.
  const [formDefaultKind, setFormDefaultKind] = React.useState<SourceKind | undefined>(undefined);
  // Bumped on every successful save AND on a fresh "+ Add source"/Cancel — folded into the
  // form's `key` below so a save that returns to the SAME target ("new" -> "new", the common
  // add-a-source case) still forces a remount, not just a target *change*. Without this, saving
  // while the form was already on "new" left the just-submitted values sitting in the fields with
  // no visible reset (cmw-source-registry-ux item 2 — reproduced live: the row landed in the
  // table but the form below looked untouched, inviting a duplicate submit).
  const [formResetKey, setFormResetKey] = React.useState(0);
  const [saving, setSaving] = React.useState(false);
  const [formError, setFormError] = React.useState<string | null>(null);
  // Visible save confirmation (item 2) — cleared at the start of the next save/retire and by
  // resetForm, so it never lingers across an unrelated later edit.
  const [saveMessage, setSaveMessage] = React.useState<string | null>(null);
  const [togglingId, setTogglingId] = React.useState<string | null>(null);
  const tableRef = React.useRef<HTMLDivElement>(null);
  const formSectionRef = React.useRef<HTMLDivElement>(null);

  const now = React.useMemo(() => new Date(), []);
  const clipSourceId = sources.find((s) => s.kind === "linkedin-x-clip")?.id ?? null;

  // Shared by "+ Add source" and the form's own Cancel (item 3) — always returns to a genuinely
  // blank, freshly-mounted form, never a no-op when the form was already on "new". `kind` is only
  // ever passed by the "Set up a clip-in source" shortcut below.
  function resetForm(kind?: SourceKind) {
    setFormTarget("new");
    setFormDefaultKind(kind);
    setFormResetKey((k) => k + 1);
    setSaveMessage(null);
  }

  async function refetchSources() {
    const res = await fetch("/api/sources", { cache: "no-store" });
    if (!res.ok) return;
    const data = (await res.json()) as SourceListResponse;
    setSources(data.items);
    setDataSource(data.source);
  }

  async function handleRefresh() {
    setRefreshing(true);
    setRefreshMessage(null);
    setRefreshErrors({});
    try {
      const res = await fetch("/api/connectors/refresh", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ lookback_days: lookbackDays }),
      });
      const body = (await res.json()) as RefreshResponse | { error: string };
      if (!res.ok) throw new Error("error" in body ? body.error : "refresh failed");
      const result = body as RefreshResponse;
      const ingested = result.refreshed.reduce((sum, r) => sum + r.ingested, 0);
      const failed = result.refreshed.filter((r) => r.error);
      setRefreshMessage(
        `Refreshed ${result.refreshed.length} source${result.refreshed.length === 1 ? "" : "s"} — ` +
          `${ingested} new item${ingested === 1 ? "" : "s"}` +
          (failed.length > 0
            ? ` (${failed.length} warned — see below)`
            : ""),
      );
      setRefreshErrors(
        Object.fromEntries(failed.map((r) => [r.source_id, r.error as string])),
      );
      await refetchSources();
      // Every mutation on this screen (this refresh updates each source's `last_refreshed`, plus
      // whatever create/edit/toggle/retire already happened) needs to invalidate the client-side
      // Router Cache too, or a later browser-back to this route can serve a snapshot from BEFORE
      // this ran (item 1's root cause — see page.tsx's `force-dynamic` comment).
      router.refresh();
    } catch (err) {
      setRefreshMessage(err instanceof Error ? err.message : "refresh failed");
    } finally {
      setRefreshing(false);
    }
  }

  async function handleToggle(source: Source, enabled: boolean) {
    setTogglingId(source.id);
    setSources((prev) => prev.map((s) => (s.id === source.id ? { ...s, enabled } : s)));
    try {
      const res = await fetch(`/api/sources/${encodeURIComponent(source.id)}`, {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ enabled }),
      });
      if (!res.ok) throw new Error("toggle failed");
      const updated = (await res.json()) as Source;
      setSources((prev) => prev.map((s) => (s.id === updated.id ? updated : s)));
      router.refresh();
    } catch {
      // Revert on failure — warns, does not silently drift from server state.
      setSources((prev) => prev.map((s) => (s.id === source.id ? source : s)));
    } finally {
      setTogglingId(null);
    }
  }

  async function handleSave(values: SourceFormValues) {
    setSaving(true);
    setFormError(null);
    setSaveMessage(null);
    try {
      const editingId = formTarget !== "new" ? formTarget.id : null;
      const res = await fetch(
        editingId ? `/api/sources/${encodeURIComponent(editingId)}` : "/api/sources",
        {
          method: editingId ? "PATCH" : "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify(values),
        },
      );
      const body = (await res.json()) as Source | { error: string };
      if (!res.ok) throw new Error("error" in body ? body.error : "save failed");
      const saved = body as Source;
      setSources((prev) =>
        editingId ? prev.map((s) => (s.id === saved.id ? saved : s)) : [...prev, saved],
      );
      setDataSource("store");
      setFormTarget("new");
      setFormDefaultKind(undefined);
      setFormResetKey((k) => k + 1);
      setSaveMessage(
        editingId
          ? `Saved changes to "${saved.display_name}".`
          : `Added "${saved.display_name}" to your sources.`,
      );
      router.refresh();
      // Move attention to the row that just landed, rather than leaving it below the fold under
      // the form the person's eyes are still on (item 2). Deferred a frame so the success alert
      // above the table has actually been committed to the DOM before measuring where to scroll.
      requestAnimationFrame(() => tableRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "save failed");
    } finally {
      setSaving(false);
    }
  }

  async function handleRetire() {
    if (formTarget === "new") return;
    setSaving(true);
    setFormError(null);
    setSaveMessage(null);
    try {
      const res = await fetch(`/api/sources/${encodeURIComponent(formTarget.id)}`, {
        method: "DELETE",
      });
      if (!res.ok) throw new Error("retire failed");
      setSources((prev) => prev.filter((s) => s.id !== formTarget.id));
      setFormTarget("new");
      setFormDefaultKind(undefined);
      setFormResetKey((k) => k + 1);
      router.refresh();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "retire failed");
    } finally {
      setSaving(false);
    }
  }

  function handleAddSourceClick() {
    setActivePanel("source");
    resetForm();
    formSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function handleClipInClick() {
    setActivePanel("clip");
    formSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  // The empty clip-in panel's shortcut when no linkedin-x-clip source exists yet — jumps to the
  // add-source panel with that kind preselected, rather than leaving the person to find "LinkedIn
  // / X (clip-in)" in the Kind dropdown themselves.
  function handleSetupClipSource() {
    setActivePanel("source");
    resetForm("linkedin-x-clip");
    formSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function handleEdit(source: Source) {
    setSaveMessage(null);
    setActivePanel("source");
    setFormTarget(source);
    // Fixes cmw-source-edit-button-scroll: this used to leave the form off-screen with no scroll,
    // exactly like "+ Add source" did before PR #83 fixed that button's own case.
    formSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  return (
    <section className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-serif text-3xl font-semibold">Source registry</h1>
          <p className="max-w-2xl text-sm text-muted-foreground">
            What the Radar reads. Every source is classified{" "}
            <b className="text-foreground">scraped-periodically</b> (legit programmatic pull) or{" "}
            <b className="text-foreground">read-as-needed</b> (clipped in by a human). Everything
            ingested lands in the content lake and is indexed on ingest.
          </p>
        </div>
        <SeededDataBadge
          seeded={dataSource === "seed"}
          seededTitle="Placeholder registry until sources are added"
        />
      </div>

      <div className="flex flex-wrap items-end gap-3 rounded-lg border bg-card p-3">
        <Field label="Default lookback window" htmlFor="lookback-days" hint="per-run parameter — overridable at each Radar run (D7)">
          <div className="flex items-center gap-1">
            <Input
              id="lookback-days"
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
        <div className="ml-auto flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={handleRefresh} disabled={refreshing}>
            <RefreshCw className={refreshing ? "h-4 w-4 animate-spin" : "h-4 w-4"} aria-hidden />
            Refresh sources now
          </Button>
          {/* These two buttons are the ONE choice point for "which panel do I want" — clicking
              either always shows exactly one form below, never both (see the module docstring).
              The active one renders solid; the other stays outline, like a segmented control. */}
          <Button
            variant={activePanel === "source" ? "default" : "outline"}
            size="sm"
            onClick={handleAddSourceClick}
          >
            + Add source
          </Button>
          <Button
            variant={activePanel === "clip" ? "default" : "outline"}
            size="sm"
            onClick={handleClipInClick}
          >
            Clip in a LinkedIn/X post
          </Button>
        </div>
      </div>

      {refreshMessage ? (
        Object.keys(refreshErrors).length > 0 ? (
          <Alert variant="warning">{refreshMessage}</Alert>
        ) : (
          <p
            className="rounded-md border bg-muted/40 px-3 py-2 text-sm text-muted-foreground"
            role="status"
          >
            {refreshMessage}
          </p>
        )
      ) : null}

      <p className="rounded-md border border-dashed bg-muted/30 px-3 py-2 text-sm text-muted-foreground">
        <b className="text-foreground">The app builds no scrapers and does no gray-market scraping (D8).</b>{" "}
        Connector credentials are held <b className="text-foreground">server-side</b>, never
        client-exposed (D14). Refresh is <b className="text-foreground">on-demand</b> — a human
        runs it (or it runs just before a Radar run); the scheduled/proactive scanner is deferred
        to v2 (§9).
      </p>

      {/* One scroll target spanning the confirmation and the table it confirms — scrolling to
          just the table would push this alert (which sits above it in flow) off the top of the
          viewport instead of bringing both into view together. */}
      <div ref={tableRef} className="flex flex-col gap-4">
        {saveMessage ? <Alert variant="success">{saveMessage}</Alert> : null}

        <SourcesTable
          sources={sources}
          now={now}
          onToggle={handleToggle}
          onEdit={handleEdit}
          togglingId={togglingId}
          refreshErrors={refreshErrors}
        />
      </div>

      <div ref={formSectionRef} className="flex flex-col gap-4">
        {activePanel === "source" ? (
          <div className="max-w-2xl">
            <SourceForm
              // Remount on target change OR on formResetKey (item 2): the form's fields are
              // initialized from `source` once at mount, so switching between "add" and a
              // specific row (or between two rows) needs a fresh instance rather than an update —
              // a keyed remount is the idiomatic reset here. `formTarget` alone isn't enough:
              // saving while already on "new" (the common add-a-source case) leaves the key
              // unchanged, so `formResetKey` (bumped on every successful save/retire and by
              // resetForm) forces the remount even then.
              key={`${formTarget === "new" ? "new" : formTarget.id}-${formResetKey}`}
              source={formTarget === "new" ? null : formTarget}
              defaultKind={formTarget === "new" ? formDefaultKind : undefined}
              onSave={handleSave}
              onRetire={formTarget !== "new" ? handleRetire : undefined}
              onCancel={() => resetForm()}
              saving={saving}
              error={formError}
            />
          </div>
        ) : (
          <div className="max-w-2xl">
            <ClipInForm
              clipSourceId={clipSourceId}
              now={now}
              onSetupSource={clipSourceId ? undefined : handleSetupClipSource}
            />
          </div>
        )}
      </div>
    </section>
  );
}
