"use client";

import { NativeSelect } from "@/components/ui/form-controls";
import { stageLabel } from "@/lib/dashboard/actions";
import type { FilterOptions, FilterState } from "@/lib/dashboard/filters";
import type { PieceStage } from "@/lib/dashboard/types";

/**
 * The D15 filter bar (voice · stage · creator · date · status) — one reusable {@link FilterState}
 * applied on top of the active tab. Native `<select>`s keep it dependency-free, keyboard-accessible,
 * and token-driven; options are derived from the live queue ({@link FilterOptions}) so they never
 * drift from the data.
 */

const DATE_OPTIONS: { label: string; value: number | null }[] = [
  { label: "Any date", value: null },
  { label: "7 days", value: 7 },
  { label: "30 days", value: 30 },
  { label: "90 days", value: 90 },
];

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

export function FilterBar({
  options,
  value,
  onChange,
}: {
  options: FilterOptions;
  value: FilterState;
  onChange: (next: FilterState) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      <span className="text-sm font-medium">Filter</span>

      <Select
        label="Voice"
        value={value.voice ?? ALL}
        onChange={(v) => onChange({ ...value, voice: v === ALL ? null : v })}
      >
        <option value={ALL}>all</option>
        {options.voices.map((v) => (
          <option key={v} value={v}>
            {v}
          </option>
        ))}
      </Select>

      <Select
        label="Stage"
        value={value.stage ?? ALL}
        onChange={(v) => onChange({ ...value, stage: v === ALL ? null : (v as PieceStage) })}
      >
        <option value={ALL}>all</option>
        {options.stages.map((s) => (
          <option key={s} value={s}>
            {stageLabel(s)}
          </option>
        ))}
      </Select>

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
        onChange={(v) => onChange({ ...value, status: v === ALL ? null : v })}
      >
        <option value={ALL}>all</option>
        {options.statuses.map((s) => (
          <option key={s} value={s}>
            {s}
          </option>
        ))}
      </Select>
    </div>
  );
}
