"use client";

import { NativeSelect } from "@/components/ui/form-controls";
import { Input } from "@/components/ui/input";
import type { FilterOptions, FilterState, SortDirection } from "@/lib/spikes/filters";
import type { SpikeStatus } from "@/lib/spikes/types";
import { spikeStatusLabel } from "@/lib/spikes/format";

/**
 * The D15 filter bar (creator · topic · date · status) + convergence sort (cmw-ui-wireframes
 * screen 5) — one reusable {@link FilterState} applied on top of the active status tab. Same
 * native-`<select>` recipe as the dashboard's `FilterBar`.
 */

const DATE_OPTIONS: { label: string; value: number | null }[] = [
  { label: "Any date", value: null },
  { label: "7 days", value: 7 },
  { label: "30 days", value: 30 },
  { label: "90 days", value: 90 },
];

const STATUS_OPTIONS: SpikeStatus[] = ["proposed", "picked", "in-flight", "vaulted"];

function Select({
  label,
  value,
  onChange,
  children,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  children: React.ReactNode;
}) {
  return (
    <label className="flex items-center gap-1.5 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <NativeSelect
        aria-label={label}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="h-9 w-auto px-2"
      >
        {children}
      </NativeSelect>
    </label>
  );
}

const ALL = "__all__";

export function SpikeFilterBar({
  options,
  value,
  onChange,
  sort,
  onSortChange,
}: {
  options: FilterOptions;
  value: FilterState;
  onChange: (next: FilterState) => void;
  sort: SortDirection;
  onSortChange: (next: SortDirection) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      <span className="text-sm font-medium">Filter (D15)</span>

      <Select
        label="Creator"
        value={value.creator ?? ALL}
        onChange={(v) => onChange({ ...value, creator: v === ALL ? null : v })}
      >
        <option value={ALL}>all</option>
        {options.creators.map((c) => (
          <option key={c} value={c}>
            {c}
          </option>
        ))}
      </Select>

      <label className="flex items-center gap-1.5 text-sm">
        <span className="text-muted-foreground">Topic</span>
        <Input
          aria-label="Topic"
          type="search"
          placeholder="keyword…"
          value={value.topic ?? ""}
          onChange={(e) => onChange({ ...value, topic: e.target.value === "" ? null : e.target.value })}
          className="h-9 w-40"
        />
      </label>

      <Select
        label="Date"
        value={value.withinDays == null ? "null" : String(value.withinDays)}
        onChange={(v) => onChange({ ...value, withinDays: v === "null" ? null : Number(v) })}
      >
        {DATE_OPTIONS.map((d) => (
          <option key={d.label} value={d.value == null ? "null" : String(d.value)}>
            {d.label}
          </option>
        ))}
      </Select>

      <Select
        label="Status"
        value={value.status ?? ALL}
        onChange={(v) => onChange({ ...value, status: v === ALL ? null : (v as SpikeStatus) })}
      >
        <option value={ALL}>all</option>
        {STATUS_OPTIONS.map((s) => (
          <option key={s} value={s}>
            {spikeStatusLabel(s)}
          </option>
        ))}
      </Select>

      <span className="ml-auto" />

      <Select
        label="Sort"
        value={sort}
        onChange={(v) => onSortChange(v as SortDirection)}
      >
        <option value="desc">convergence ↓</option>
        <option value="asc">convergence ↑</option>
      </Select>
    </div>
  );
}
