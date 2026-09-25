"use client";

import * as React from "react";
import Link from "next/link";
import { RefreshCw } from "lucide-react";

import { SpikeDetailPanel } from "@/components/spikes/spike-detail-panel";
import { SpikeFilterBar } from "@/components/spikes/spike-filter-bar";
import { SpikesTable } from "@/components/spikes/spikes-table";
import { SeededDataBadge } from "@/components/dashboard/seeded-data-badge";
import { Button } from "@/components/ui/button";
import {
  applyFilters,
  applyStatusTab,
  EMPTY_FILTERS,
  filterOptions,
  sortByConvergence,
  STATUS_TABS,
  type FilterState,
  type SortDirection,
  type StatusTabKey,
} from "@/lib/spikes/filters";
import type { SpikeListResponse } from "@/lib/spikes/types";
import { cn } from "@/lib/utils";

/**
 * The Spikes & Vault browser (cmw-ui-wireframes screen 5): status tabs over the one shared pool,
 * the D15 filter bar + convergence sort, the spike table, and a selected-spike detail panel.
 * Ownership is attribution, not a lock (D15) — every row's hand-off action is offered to anyone.
 */
export function SpikeVaultBrowser({ initial }: { initial: SpikeListResponse }) {
  const [spikes, setSpikes] = React.useState(initial.items);
  const [dataSource, setDataSource] = React.useState<SpikeListResponse["source"]>(initial.source);
  const [tab, setTab] = React.useState<StatusTabKey>("all");
  const [filters, setFilters] = React.useState<FilterState>(EMPTY_FILTERS);
  const [sort, setSort] = React.useState<SortDirection>("desc");
  const [selectedId, setSelectedId] = React.useState<string | null>(initial.items[0]?.id ?? null);
  const [refreshing, setRefreshing] = React.useState(false);

  const now = React.useMemo(() => new Date(), []);

  const tabItems = React.useMemo(() => applyStatusTab(spikes, tab), [spikes, tab]);
  const options = React.useMemo(() => filterOptions(tabItems), [tabItems]);
  const filtered = React.useMemo(() => applyFilters(tabItems, filters, now), [tabItems, filters, now]);
  const visible = React.useMemo(() => sortByConvergence(filtered, sort), [filtered, sort]);

  const counts = React.useMemo(() => {
    const c: Partial<Record<StatusTabKey, number>> = {};
    for (const t of STATUS_TABS) c[t.key] = applyStatusTab(spikes, t.key).length;
    return c;
  }, [spikes]);

  const selected = visible.find((s) => s.id === selectedId) ?? visible[0] ?? null;

  async function refresh() {
    setRefreshing(true);
    try {
      const res = await fetch("/api/spikes", { cache: "no-store" });
      if (res.ok) {
        const data = (await res.json()) as SpikeListResponse;
        setSpikes(data.items);
        setDataSource(data.source);
      }
    } finally {
      setRefreshing(false);
    }
  }

  const onTab = (next: StatusTabKey) => {
    setTab(next);
    setFilters(EMPTY_FILTERS);
  };

  return (
    <section className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-serif text-3xl font-semibold">Spikes &amp; Vault</h1>
          <p className="max-w-2xl text-sm text-muted-foreground">
            A shared, team-visible pool. Every spike is attributed to its creator and origin
            (run/narrative) and carries a convergence score and status.{" "}
            <b className="text-foreground">Ownership is attribution, not a lock</b> — anyone can
            pick or advance any spike.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <SeededDataBadge
            seeded={dataSource === "seed"}
            seededTitle="Placeholder pool until a Radar run writes real spikes"
          />
          <Button variant="outline" size="sm" onClick={refresh} disabled={refreshing}>
            <RefreshCw className={cn("h-4 w-4", refreshing && "animate-spin")} aria-hidden />
            Refresh
          </Button>
          <Button asChild size="sm">
            <Link href="/narrative">Run Radar</Link>
          </Button>
        </div>
      </div>

      <div role="tablist" aria-label="Spike status" className="flex flex-wrap gap-1 border-b">
        {STATUS_TABS.map((t) => (
          <button
            key={t.key}
            role="tab"
            aria-selected={tab === t.key}
            onClick={() => onTab(t.key)}
            className={cn(
              "flex items-center gap-2 border-b-2 px-3 py-2 text-sm font-medium transition-colors",
              tab === t.key
                ? "border-primary text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground",
            )}
          >
            {t.label}
            {counts[t.key] ? (
              <span className="rounded-full bg-muted px-1.5 text-xs text-muted-foreground">
                {counts[t.key]}
              </span>
            ) : null}
          </button>
        ))}
      </div>

      <SpikeFilterBar
        options={options}
        value={filters}
        onChange={setFilters}
        sort={sort}
        onSortChange={setSort}
      />

      <SpikesTable spikes={visible} selectedId={selected?.id ?? null} onSelect={setSelectedId} />

      {selected ? <SpikeDetailPanel spike={selected} /> : null}
    </section>
  );
}
