import { cn } from "@/lib/utils";

// Shared form primitives for the labels/selects/toggles the `components/ui/` kit didn't already
// own — promoted here from the old per-screen `sources/form-controls.tsx` fork once parallel
// screen work finished (that fork and its `voice-kit/`/`piece-detail/` copies were all the same
// recipe kept "scoped so this screen stays self-contained"). Single-line text is the shared
// `ui/input.tsx` `Input`, multiline is the shared `ui/textarea.tsx` `TextArea`; this module keeps
// only what those two don't cover.

const FIELD_CLASSES =
  "w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground " +
  "placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 " +
  "focus-visible:ring-ring focus-visible:ring-offset-2 ring-offset-background " +
  // Same flat "muted" disabled collapse as Input/Button/TextArea (cmw-interactive-state-affordance),
  // never a translucent fade.
  "disabled:cursor-not-allowed disabled:border-muted disabled:bg-muted disabled:text-muted-foreground";

export function Field({
  label,
  htmlFor,
  hint,
  children,
}: {
  label: string;
  htmlFor: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={htmlFor} className="text-sm font-medium">
        {label}
      </label>
      {children}
      {hint ? <span className="text-xs text-muted-foreground">{hint}</span> : null}
    </div>
  );
}

export function NativeSelect(props: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...props} className={cn(FIELD_CLASSES, props.className)} />;
}

/** An accessible on/off toggle switch (screen 7's "On" column) — a native checkbox, restyled. */
export function ToggleSwitch({
  checked,
  onChange,
  label,
  disabled = false,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
  label: string;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cn(
        "relative h-5 w-9 shrink-0 rounded-full border transition-colors disabled:cursor-not-allowed disabled:opacity-50",
        checked ? "border-primary bg-primary" : "border-input bg-muted",
      )}
    >
      <span
        className={cn(
          "absolute top-0.5 h-3.5 w-3.5 rounded-full bg-background transition-transform",
          checked ? "translate-x-4" : "translate-x-0.5",
        )}
      />
    </button>
  );
}
