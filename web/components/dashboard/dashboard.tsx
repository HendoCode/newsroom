"use client";

import * as React from "react";
import Link from "next/link";
import { RefreshCw } from "lucide-react";

import { FilterBar } from "@/components/dashboard/filter-bar";
import { PieceCard } from "@/components/dashboard/piece-card";
import { SeededDataBadge } from "@/components/dashboard/seeded-data-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { stageLabel } from "@/lib/dashboard/actions";
import {
  buildInbox,
  libraryPieces,
  librarySummary,
  machineWorking,
} from "@/lib/dashboard/desk";
import { applyFilters, EMPTY_FILTERS, filterOptions, type FilterState } from "@/lib/dashboard/filters";
import type { DashboardResponse, QueueItem } from "@/lib/dashboard/types";
import { relativeTime } from "@/lib/format/relative-time";
import { cn } from "@/lib/utils";

/**
 * The dashboard, redesigned as the operator desk (Concept A, cmw-evolution-ux-audit report §6/§7,
 * captain-approved 2026-08-31): ONE shared queue rendered as THREE honest sections —
 *
 *  - **Inbox** — only real human-actionable decisions, grouped by the decision itself, built on
 *    the expanded `needsMyAction` predicate (PR #140) consumed unchanged (`lib/dashboard/desk.ts`).
 *  - **Machine strip** — ambient, non-clickable visibility of the pieces currently running a
 *    batch job. Not a queue you work from; proof that things are moving.
 *  - **Library** — every piece across every stage (published/finalized included), filterable via
 *    the D15 bar, nothing hidden, with honest in-flight-vs-terminal counts.
 *
 * Replaces the old five saved-filter tabs (Needs my action / My pieces / All in flight / Spikes /
 * Sources): the Spikes and Sources tabs duplicated the `/spikes` and `/sources` screens (report
 * §2.3 ship-now bugs), "All in flight" lied by including terminal pieces (the Library fixes that),
 * and the attribution predicate lives on as the Inbox's grouping, not a tab. Attribution is
 * display-only throughout — never a permission gate (flat auth, §1.17). Server-rendered initial
 * data is refetchable through the BFF route (`/api/dashboard`).
 */
export function Dashboard({
  initial,
  email,
}: {
  initial: DashboardResponse;
  email: string | null | undefined;
}) {
  const [items, setItems] = React.useState<QueueItem[]>(initial.items);
  const [source, setSource] = React.useState<DashboardResponse["source"]>(initial.source);
  const [filters, setFilters] = React.useState<FilterState>(EMPTY_FILTERS);
  const [refreshing, setRefreshing] = React.useState(false);

  // One clock for relative times and the date filter axis, captured on mount so rendering is
  // stable across re-renders.
  const now = React.useMemo(() => new Date(), []);

  const inboxGroups = React.useMemo(() => buildInbox(items, email), [items, email]);
  const inboxCount = React.useMemo(
    () => inboxGroups.reduce((n, g) => n + g.entries.length, 0),
    [inboxGroups],
  );
  const running = React.useMemo(() => machineWorking(items), [items]);
  const library = React.useMemo(() => libraryPieces(items), [items]);
  const summary = React.useMemo(() => librarySummary(items), [items]);

  // The D15 bar filters ONLY the Library — the Inbox is a decision list and the strip is ambient;
  // neither should be narrowed away by a stale filter the user set on the Library.
  const options = React.useMemo(() => filterOptions(library), [library]);
  const visibleLibrary = React.useMemo(
    () => applyFilters(library, filters, now),
    [library, filters, now],
  );

  async function refresh() {
    setRefreshing(true);
    try {
      const res = await fetch("/api/dashboard", { cache: "no-store" });
      if (res.ok) {
        const data = (await res.json()) as DashboardResponse;
        setItems(data.items);
        setSource(data.source);
      }
    } finally {
      setRefreshing(false);
    }
  }

  async function archiveItem(item: QueueItem) {
    const res = await fetch(`/api/pieces/${encodeURIComponent(item.id)}/archive`, {
      method: "POST",
    });
    if (res.ok) {
      // Optimistic local removal — the server already excludes archived pieces from the queue
      // (`agents/app/dashboard.py`'s `build_queue`), so this just mirrors that without a round
      // trip. The item leaves every section at once (inbox, strip, library) because all three
      // derive from this one `items` state.
      setItems((prev) => prev.filter((it) => !(it.kind === "piece" && it.id === item.id)));
    }
  }

  async function renameItem(item: QueueItem, newTitle: string) {
    const res = await fetch(`/api/pieces/${encodeURIComponent(item.id)}/title`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: newTitle }),
    });
    if (res.ok) {
      // Optimistically update title in local state
      setItems((prev) =>
        prev.map((it) =>
          it.kind === "piece" && it.id === item.id ? { ...it, title: newTitle } : it
        )
      );
    }
  }

  return (
    <section className="flex flex-col gap-8">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-serif text-3xl font-semibold">Dashboard</h1>
          <p className="max-w-2xl text-sm text-muted-foreground">
            Your desk in three sections: an Inbox of the decisions only a human can make, an
            ambient strip of what the machine is working on, and the Library — every piece across
            every stage, nothing hidden.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <SeededDataBadge
            seeded={source === "seed"}
            seededTitle="Placeholder data until real work is saved"
          />
          <Button variant="outline" size="sm" onClick={refresh} disabled={refreshing}>
            <RefreshCw className={cn("h-4 w-4", refreshing && "animate-spin")} aria-hidden />
            Refresh
          </Button>
        </div>
      </div>

      {/* First-mile cluster (report §8: New idea | Radar | Vault) */}
      <div className="flex flex-wrap items-center gap-2 rounded-lg border border-dashed p-3">
        <span className="text-sm text-muted-foreground">First mile:</span>
        <Button asChild size="sm">
          <Link href="/pieces/new">Start a piece from my idea</Link>
        </Button>
        <Button asChild size="sm" variant="outline">
          <Link href="/narrative">Run the Radar</Link>
        </Button>
        <Button asChild size="sm" variant="outline">
          <Link href="/spikes">Open the Vault</Link>
        </Button>
      </div>

      <Inbox groups={inboxGroups} count={inboxCount} onArchive={archiveItem} onRename={renameItem} now={now} email={email} />
      <MachineStrip running={running} now={now} email={email} />
      <Library
        library={library}
        visible={visibleLibrary}
        summary={summary}
        options={options}
        filters={filters}
        onFiltersChange={setFilters}
        onArchive={archiveItem}
        onRename={renameItem}
        now={now}
        email={email}
      />
    </section>
  );
}

/* --- Inbox — only human decisions, grouped by the decision ---------------------------------- */

function Inbox({
  groups,
  count,
  onArchive,
  onRename,
  now,
  email,
}: {
  groups: ReturnType<typeof buildInbox>;
  count: number;
  onArchive: (item: QueueItem) => void | Promise<void>;
  onRename?: (item: QueueItem, newTitle: string) => void | Promise<void>;
  now: Date;
  email: string | null | undefined;
}) {
  return (
    <section aria-labelledby="desk-inbox-heading" className="flex flex-col gap-3">
      <div className="flex flex-wrap items-baseline gap-2">
        <h2 id="desk-inbox-heading" className="font-serif text-xl font-semibold">
          Inbox
        </h2>
        <span className="text-sm text-muted-foreground">
          {count === 0 ? "nothing needs you" : `${count} decision${count === 1 ? "" : "s"} need you`}
        </span>
      </div>

      {groups.length === 0 ? (
        <div className="rounded-lg border border-dashed bg-card p-6 text-center">
          <p className="font-serif text-lg font-semibold">Nothing needs you right now</p>
          <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
            Decisions land here when they need you — answer an interview, decide whether there&rsquo;s
            enough to draft, close a review, sign off, resolve lessons, recover a failure. What
            the machine is doing instead is on the strip below; everything else is in the Library.
          </p>
        </div>
      ) : (
        groups.map((group) => (
          <div key={group.def.key} className="flex flex-col gap-2">
            <div className="flex flex-wrap items-baseline gap-2">
              <h3 className="text-sm font-semibold uppercase tracking-wide">
                {group.def.label}
              </h3>
              <span className="rounded-full bg-muted px-1.5 text-xs text-muted-foreground">
                {group.entries.length}
              </span>
              <span className="text-xs text-muted-foreground">{group.def.description}</span>
            </div>
            <div className="flex flex-col gap-3">
              {group.entries.map(({ item }) => (
                <PieceCard
                  key={`${item.kind}:${item.id}`}
                  item={item}
                  email={email}
                  showWhy
                  onArchive={item.kind === "piece" ? onArchive : undefined}
                  onRename={item.kind === "piece" ? onRename : undefined}
                  now={now}
                />
              ))}
            </div>
          </div>
        ))
      )}
    </section>
  );
}

/* --- Machine strip — ambient, non-clickable visibility of running batch work ---------------- */

function MachineStrip({
  running,
  now,
  email,
}: {
  running: QueueItem[];
  now: Date;
  email: string | null | undefined;
}) {
  return (
    <section aria-labelledby="desk-machine-heading" className="flex flex-col gap-2">
      <div className="flex flex-wrap items-baseline gap-2">
        <h2 id="desk-machine-heading" className="font-serif text-xl font-semibold">
          Machine working
        </h2>
        <span className="text-sm text-muted-foreground">
          {running.length === 0
            ? "idle"
            : `${running.length} piece${running.length === 1 ? "" : "s"} in motion`}
        </span>
      </div>

      {running.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          Nothing is in motion right now — drafting, review, and finalizing show up here when
          the machine has work to do.
        </p>
      ) : (
        <div className="rounded-lg border bg-muted/40 p-3">
          <ul className="flex flex-col gap-1.5">
            {running.map((item) => (
              <li key={item.id} className="flex flex-wrap items-baseline gap-x-2 text-sm">
                <span className="h-2 w-2 shrink-0 animate-pulse rounded-full bg-primary" aria-hidden />
                <Badge variant="outline">{item.stage ? stageLabel(item.stage) : "Working"}</Badge>
                <span className="font-serif font-semibold">{item.title}</span>
                {item.owner && item.owner === email ? (
                  <span className="text-xs text-muted-foreground">· yours</span>
                ) : null}
                <span className="text-xs text-muted-foreground" title="Last write of any kind, including the running job">
                  {item.updated_at ? `updated ${relativeTime(item.updated_at, now)}` : "working…"}
                </span>
              </li>
            ))}
          </ul>
          <p className="mt-2 text-xs text-muted-foreground">
            Ambient only — nothing here needs a click. Failures surface in the Inbox as “Recover a
            failure”; full history is in the Library.
          </p>
        </div>
      )}
    </section>
  );
}

/* --- Library — every piece across every stage, filterable, nothing hidden -------------------- */

function Library({
  library,
  visible,
  summary,
  options,
  filters,
  onFiltersChange,
  onArchive,
  onRename,
  now,
  email,
}: {
  library: QueueItem[];
  visible: QueueItem[];
  summary: ReturnType<typeof librarySummary>;
  options: ReturnType<typeof filterOptions>;
  filters: FilterState;
  onFiltersChange: (next: FilterState) => void;
  onArchive: (item: QueueItem) => void | Promise<void>;
  onRename?: (item: QueueItem, newTitle: string) => void | Promise<void>;
  now: Date;
  email: string | null | undefined;
}) {
  // Honest lifecycle accounting — the old "All in flight" tab included published/finalized pieces
  // (report §2.3); the Library names the split instead of hiding it in one count.
  const counts: string[] = [`${summary.total} piece${summary.total === 1 ? "" : "s"}`];
  if (summary.inFlight > 0) counts.push(`${summary.inFlight} in flight`);
  if (summary.done > 0) counts.push(`${summary.done} done`);
  if (summary.failed > 0) counts.push(`${summary.failed} failed`);

  return (
    <section
      id="library"
      aria-labelledby="desk-library-heading"
      className="flex scroll-mt-28 flex-col gap-3"
    >
      <div className="flex flex-wrap items-baseline gap-2">
        <h2 id="desk-library-heading" className="font-serif text-xl font-semibold">
          Library
        </h2>
        <span className="text-sm text-muted-foreground">{counts.join(" · ")}</span>
      </div>
      <p className="text-sm text-muted-foreground">
        Every piece across every stage — published and finalized included — regardless of who owns
        it. Filter; nothing here is hidden.
      </p>

      {library.length > 0 ? <FilterBar options={options} value={filters} onChange={onFiltersChange} /> : null}

      {library.length === 0 ? (
        <div className="rounded-lg border border-dashed bg-card p-6 text-center">
          <p className="font-serif text-lg font-semibold">No pieces yet</p>
          <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
            Start a piece from your idea above, or pick a spike from the Vault.
          </p>
        </div>
      ) : visible.length === 0 ? (
        <p className="text-sm text-muted-foreground">No pieces match the current filters.</p>
      ) : (
        <div className="flex flex-col gap-3">
          {visible.map((item) => (
            <PieceCard
              key={item.id}
              item={item}
              email={email}
              onArchive={onArchive}
              onRename={onRename}
              now={now}
            />
          ))}
        </div>
      )}
    </section>
  );
}
